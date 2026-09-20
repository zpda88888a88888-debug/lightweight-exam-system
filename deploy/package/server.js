#!/usr/bin/env node
/**
 * 极轻量级客观题考试系统 — 内置 Web 服务器
 *
 * 零第三方依赖，只用 Node 内置模块；因此内网服务器**不需要 npm install，也不需要 Nginx**。
 * 使用 CommonJS（require），Node 14+ 均可直接运行，无需 package.json。
 *
 * 职责：
 *   1. 托管前端构建产物（dist），
 *   2. 把 /api/* 反向代理到本机 Python 后端（默认 127.0.0.1:8000）。
 *
 * 设计要点：
 *   - 前端使用 hash 路由，刷新任意页面只请求 index.html / admin.html，无需 rewrite 规则。
 *   - 后端只监听 127.0.0.1，由本进程统一对外，减少暴露面。
 *   - 带 hash 的静态资源长缓存；html 不缓存，发版后立即生效。
 *
 * 环境变量：
 *   PORT             对外监听端口，默认 8080
 *   HOST             对外监听地址，默认 0.0.0.0
 *   BACKEND_ORIGIN   后端地址，默认 http://127.0.0.1:8000
 *   PROXY_TIMEOUT_MS 代理超时毫秒，默认 60000
 */

'use strict'

const http = require('node:http')
const fs = require('node:fs')
const path = require('node:path')
const { URL } = require('node:url')

const ROOT = __dirname
const DIST = path.join(ROOT, 'dist')
const PORT = Number(process.env.PORT || 8080)
const HOST = process.env.HOST || '0.0.0.0'
const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN || 'http://127.0.0.1:8000'
const PROXY_TIMEOUT_MS = Number(process.env.PROXY_TIMEOUT_MS || 60000)

const backendUrl = new URL(BACKEND_ORIGIN)

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.ico': 'image/x-icon',
  '.webp': 'image/webp',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.map': 'application/json; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
  '.csv': 'text/csv; charset=utf-8',
}

if (!fs.existsSync(DIST)) {
  console.error('[web] 找不到前端目录：' + DIST)
  console.error('[web] 请确认 dist/ 与 server.js 在同一目录下。')
  process.exit(1)
}

const server = http.createServer((req, res) => {
  let pathname
  try {
    pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname)
  } catch (err) {
    return sendText(res, 400, '请求路径非法')
  }

  if (pathname === '/api' || pathname.indexOf('/api/') === 0) {
    return proxyToBackend(req, res)
  }
  return serveStatic(req, res, pathname)
})

// --------------------------------------------------------------------------
// 静态文件
// --------------------------------------------------------------------------

function serveStatic(req, res, pathname) {
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.writeHead(405, { Allow: 'GET, HEAD' })
    return res.end()
  }

  let relative = pathname === '/' ? 'index.html' : pathname.replace(/^\/+/, '')

  // 无扩展名的路径（目录或 hash 路由）统一补成 html
  if (!path.extname(relative)) {
    relative = relative.charAt(relative.length - 1) === '/'
      ? relative + 'index.html'
      : relative + '.html'
  }

  const target = path.resolve(DIST, relative)

  // 防目录穿越：解析后必须仍在 DIST 之内
  if (target !== DIST && target.indexOf(DIST + path.sep) !== 0) {
    return sendText(res, 403, '禁止访问')
  }

  fs.stat(target, function (err, stat) {
    if (err || !stat.isFile()) {
      return sendText(res, 404, '未找到：' + pathname)
    }

    const ext = path.extname(target).toLowerCase()
    const isHtml = ext === '.html'
    const headers = {
      'Content-Type': MIME[ext] || 'application/octet-stream',
      'Content-Length': stat.size,
      // 构建产物文件名带 hash → 长缓存；html 不缓存 → 发版即时生效
      'Cache-Control': isHtml ? 'no-cache' : 'public, max-age=31536000, immutable',
      'X-Content-Type-Options': 'nosniff',
    }

    if (req.method === 'HEAD') {
      res.writeHead(200, headers)
      return res.end()
    }

    res.writeHead(200, headers)
    const stream = fs.createReadStream(target)
    stream.on('error', function () {
      res.destroy()
    })
    stream.pipe(res)
  })
}

function sendText(res, status, message) {
  const body = Buffer.from(message, 'utf8')
  res.writeHead(status, {
    'Content-Type': 'text/plain; charset=utf-8',
    'Content-Length': body.length,
  })
  res.end(body)
}

// --------------------------------------------------------------------------
// /api 反向代理
// --------------------------------------------------------------------------

// 交卷峰值可能数百请求同时到达：不限制后端连接数，避免在代理层排队失败
const proxyAgent = new http.Agent({ keepAlive: true, maxSockets: Infinity })

function proxyToBackend(req, res) {
  const headers = Object.assign({}, req.headers, {
    host: backendUrl.host,
    'x-forwarded-for': req.socket.remoteAddress || '',
    'x-forwarded-proto': 'http',
  })

  const proxyReq = http.request(
    {
      hostname: backendUrl.hostname,
      port: backendUrl.port || 80,
      path: req.url,
      method: req.method,
      headers: headers,
      agent: proxyAgent,
    },
    function (proxyRes) {
      res.writeHead(proxyRes.statusCode || 502, proxyRes.headers)
      proxyRes.pipe(res)
    },
  )

  proxyReq.setTimeout(PROXY_TIMEOUT_MS, function () {
    proxyReq.destroy(new Error('后端响应超时'))
  })

  proxyReq.on('error', function (err) {
    if (res.headersSent) {
      return res.destroy()
    }
    console.error('[web] 代理到后端失败：' + err.message)
    sendText(res, 502, '后端服务不可用，请确认后端已启动（' + BACKEND_ORIGIN + '）')
  })

  req.on('aborted', function () {
    proxyReq.destroy()
  })
  req.pipe(proxyReq)
}

server.keepAliveTimeout = 65000
server.headersTimeout = 66000

server.listen(PORT, HOST, function () {
  console.log('[web] 前端静态目录：' + DIST)
  console.log('[web] /api 反向代理  -> ' + BACKEND_ORIGIN)
  console.log('[web] 监听地址        -> http://' + HOST + ':' + PORT)
  console.log('[web] 考生端 /          管理端 /admin.html')
})

;['SIGINT', 'SIGTERM'].forEach(function (signal) {
  process.on(signal, function () {
    console.log('[web] 收到 ' + signal + '，正在退出…')
    server.close(function () {
      process.exit(0)
    })
    setTimeout(function () {
      process.exit(0)
    }, 3000).unref()
  })
})
