(function () {
    "use strict";

    const selector =
        "span.arithmatex[data-htmlrender-arithmatex], " +
        "div.arithmatex[data-htmlrender-arithmatex]";
    const containers = document.querySelectorAll(selector);

    for (const container of containers) {
        let tex = container.textContent || "";
        let displayMode = container.tagName === "DIV";

        if (tex.startsWith("\\(") && tex.endsWith("\\)")) {
            tex = tex.slice(2, -2);
            displayMode = false;
        } else if (tex.startsWith("\\[") && tex.endsWith("\\]")) {
            tex = tex.slice(2, -2);
            displayMode = true;
        }

        try {
            katex.render(tex, container, {
                displayMode: displayMode,
                throwOnError: true,
            });
        } catch (_error) {
            container.textContent = tex;
        }
    }
})();
