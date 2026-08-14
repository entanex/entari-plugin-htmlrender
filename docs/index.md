---
title: entari-plugin-htmlrender
description: 从首次渲染到扩展开发与项目维护的统一文档入口
icon: lucide/image
hide:
  - navigation
  - toc
  - footer
---

<div class="htmlrender-home">

<section class="htmlrender-hero" aria-labelledby="htmlrender-hero-title">
  <div class="htmlrender-hero__graphic" aria-hidden="true">
    <svg viewBox="0 0 1440 760" preserveAspectRatio="xMidYMid slice">
      <defs>
        <filter id="htmlrender-glow" x="-100%" y="-100%" width="300%" height="300%">
          <feGaussianBlur stdDeviation="5" />
        </filter>
      </defs>
      <g class="htmlrender-tracks htmlrender-tracks--soft">
        <path d="M-120 682 C210 665 266 258 533 275 S827 654 1114 578 S1313 258 1548 228" />
        <path d="M-92 710 C238 692 304 294 544 305 S814 621 1088 554 S1302 292 1531 260" />
        <path d="M-68 736 C257 720 338 331 559 338 S810 591 1065 530 S1290 326 1510 295" />
        <path d="M192 -68 C246 153 319 212 510 210 S816 97 995 216 S1146 523 1510 472" />
        <path d="M256 -76 C294 125 354 180 523 184 S804 108 970 228 S1132 492 1502 444" />
        <path d="M319 -80 C346 99 396 151 538 160 S792 124 944 239 S1113 461 1484 417" />
      </g>
      <g class="htmlrender-tracks htmlrender-tracks--bright">
        <path d="M-96 620 C234 605 286 214 518 236 S826 689 1138 605 S1323 205 1532 178" />
        <path d="M134 -70 C202 181 295 248 494 238 S831 66 1020 205 S1162 558 1522 506" />
        <path d="M-42 430 C243 412 338 392 548 414 S842 530 1082 488 S1315 368 1498 362" />
      </g>
      <g class="htmlrender-track-nodes">
        <circle cx="518" cy="236" r="18" filter="url(#htmlrender-glow)" />
        <circle cx="518" cy="236" r="3.2" />
        <circle cx="1082" cy="488" r="16" filter="url(#htmlrender-glow)" />
        <circle cx="1082" cy="488" r="3" />
        <circle cx="1020" cy="205" r="12" filter="url(#htmlrender-glow)" />
        <circle cx="1020" cy="205" r="2.6" />
      </g>
    </svg>
  </div>

  <div class="htmlrender-hero__inner">
    <div class="htmlrender-hero__content">
      <p class="htmlrender-eyebrow">
        <span></span>
        Entari rendering infrastructure
      </p>
      <h1 id="htmlrender-hero-title">
        把内容渲染成<strong>图片。</strong>
      </h1>
      <p class="htmlrender-hero__lead">
        一套 API 接收 HTML、Markdown、纯文本与 Jinja 模板；可插拔 Provider 在浏览器与原生后端之间选择，稳定产出类型化图片。
      </p>
      <div class="htmlrender-hero__actions">
        <a class="md-button md-button--primary" href="start/quickstart/">
          开始第一次渲染
          <span aria-hidden="true">→</span>
        </a>
        <a class="md-button" href="guides/">
          浏览使用指南
        </a>
      </div>
      <ul class="htmlrender-hero__facts" aria-label="项目能力概览">
        <li><strong>多种内容</strong> HTML · Markdown · Text · Jinja</li>
        <li><strong>按需选型</strong> Browser · Native</li>
        <li><strong>图片就绪</strong> PNG · JPEG · 尺寸信息</li>
      </ul>
    </div>

    <div class="htmlrender-preview" aria-hidden="true">
      <div class="htmlrender-preview__bar">
        <span class="htmlrender-preview__controls">
          <i></i><i></i><i></i>
        </span>
        <span class="htmlrender-preview__history">
          <i></i><i></i>
        </span>
        <span class="htmlrender-preview__address">
          <i></i><b></b>
        </span>
        <span class="htmlrender-preview__tools">
          <i></i><i></i>
        </span>
      </div>
      <div class="htmlrender-preview__canvas">
        <div class="htmlrender-entari__nav">
          <span class="htmlrender-entari__brand">
            <i></i>
            <b></b>
          </span>
          <span class="htmlrender-entari__links">
            <i></i><i></i><i></i>
          </span>
        </div>
        <div class="htmlrender-entari__hero">
          <span class="htmlrender-entari__ring"></span>
          <div class="htmlrender-entari__wordmark">
            <i></i><i></i>
          </div>
          <span class="htmlrender-entari__tagline"></span>
          <div class="htmlrender-entari__actions">
            <span><i></i></span>
            <code><i></i><i></i><i></i></code>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>

</div>

## 按任务进入

| 现在要做什么 | 从这里开始 |
| --- | --- |
| 安装插件并完成第一张图片 | [开始使用](start/index.md) |
| 渲染 HTML、Markdown、文本、模板或图形场景 | [使用指南](guides/index.md) |
| 配置 Provider、资源策略并部署到生产环境 | [配置与部署](configuration/index.md) |
| 核对类型、方法、返回值与失败语义 | [API 参考](reference/index.md) |
| 实现第三方 Provider 或理解资源管线 | [扩展开发](extensions/index.md) |
| 贡献代码、维护 CI 或发布版本 | [维护者指南](project/index.md) |

首次使用时依次阅读“开始使用”和“使用指南”；其余章节按任务查阅，不需要线性通读。
