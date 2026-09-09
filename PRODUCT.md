# Product

## Register

product

## Platform

web

## Users

主要用户是正在本地开发和调试 Django 项目的 Python 开发者。他们需要快速理解应用实际收到的 HTTP 请求、应用返回的响应，以及在不重新触发第三方事件的情况下复现 webhook、回调和 API 请求。

## Product Purpose

django-http-inspector 是一个嵌入现有 Django 项目的开发期 HTTP Inspector。用户安装应用、包装一次 WSGI 或 ASGI application，继续使用原来的服务启动方式，即可在同一端口的 `/__inspect/` 查看请求与响应，并将保存的请求通过真实 HTTP 连接重新发送到捕获时确定的完整 URL。

成功意味着开发者从发现异常请求到查看上下文、修改并 replay 的路径足够短，同时不需要部署独立代理、额外端口或后台服务。

## Positioning

为 Django 原生开发流程提供类似 ngrok Traffic Inspector 的请求检查与真实 HTTP replay 能力，而不要求 django-http-inspector 自己充当反向代理或公网隧道。

## Brand Personality

专业、克制、高密度。界面服务于诊断任务，强调信息清晰、状态可信和操作效率，不用装饰性视觉抢夺用户注意力。

## Anti-references

- 不逐像素复制 ngrok 的品牌、配色或视觉资产；只学习其信息架构、主从布局和操作路径。
- 不做强调氛围而牺牲可读性的终端风界面。
- 不使用大面积装饰、冗余卡片、夸张圆角或与任务无关的动画。
- 不把简单的本地调试工具包装成复杂的可观测性平台。

## Design Principles

- 请求列表到请求详情再到 replay 的价值路径最短。
- 保留真实 HTTP 语义，尤其是捕获时的完整有效 URL和网络级 replay；同时诚实呈现 WSGI 已被服务器规范化的边界。
- Inspector UI 与业务 Django middleware 链隔离，调试工具自身必须可靠可达。
- 高信息密度必须建立在清晰层级和一致组件之上。
- MVP 保持本地、单进程、少配置、低运维成本。

## Accessibility & Inclusion

MVP 保证键盘可操作、可见焦点、基本文字对比和不只依赖颜色表达状态，但暂不将完整 WCAG 2.1 AA 合规列为正式验收门槛。
