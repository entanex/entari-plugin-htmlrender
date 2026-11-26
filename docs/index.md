---
title: entari-plugin-htmlrender
description: 面向 Entari 的图片渲染插件：支持 Takumi 原生渲染、Playwright 浏览器渲染与 Pillow/Skia 绘图
icon: lucide/image
hide:
  - navigation
  - toc
  - footer
---

<div class="htmlrender-home">

<a class="htmlrender-announcement" href="configuration/takumi/">
  <strong>Takumi 原生渲染</strong>
  <span>无需安装浏览器，进程内直接将 HTML、Markdown 与模板渲染为图片。</span>
  <span class="htmlrender-announcement__link">查看配置</span>
</a>

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
      <h1 id="htmlrender-hero-title">
        把内容渲染成图片。
      </h1>
      <p class="htmlrender-hero__lead">
        为 Entari 提供简洁可靠的图片渲染能力：支持 HTML、Markdown、纯文本与 Jinja2 模板，也内置 Pillow 与 Skia Python 绘图。
      </p>
      <div class="htmlrender-hero__actions">
        <a class="md-button md-button--primary" href="start/quickstart/">
          快速开始
          <span aria-hidden="true">→</span>
        </a>
        <a class="md-button" href="guides/rendering/">
          使用指南
        </a>
        <a class="md-button" href="configuration/overview/">
          配置参考
        </a>
      </div>
      <ul class="htmlrender-hero__facts" aria-label="核心特性概览">
        <li><strong>多种输入</strong> HTML · Markdown · 纯文本 · Jinja2</li>
        <li><strong>原生引擎</strong> Takumi 零浏览器 · Playwright 按需扩展</li>
        <li><strong>独立绘图</strong> Pillow · Skia Python 绘图与热重载</li>
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
