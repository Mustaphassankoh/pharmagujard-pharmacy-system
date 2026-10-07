(function () {
    "use strict";

    const iconRules = [
        [/register|create.*workspace/i, "building-plus"], [/sign in|login/i, "log-in"],
        [/back/i, "arrow-left"], [/\badd\b|\bnew\b/i, "plus"], [/save/i, "save"],
        [/edit/i, "pencil"], [/delete|remove/i, "trash-2"], [/cancel|clear|reset/i, "x"],
        [/search/i, "search"], [/filter/i, "sliders-horizontal"], [/download|export/i, "download"],
        [/view|details/i, "eye"], [/history/i, "history"], [/refresh|adjust/i, "refresh-cw"],
        [/submit/i, "send"], [/approve/i, "check-check"], [/activate/i, "power"],
        [/retire/i, "archive"], [/password/i, "key-round"], [/deactivate/i, "user-x"],
        [/resume/i, "play"], [/dispense|confirm/i, "check-circle"],
        [/medicine/i, "pill"], [/categor/i, "tags"], [/inventory/i, "boxes"],
        [/batch/i, "package"], [/low stock/i, "triangle-alert"], [/expir|fefo/i, "calendar-clock"],
        [/stock transaction/i, "history"], [/direct sale/i, "shopping-cart"],
        [/external prescription/i, "file-text"], [/consultation/i, "stethoscope"],
        [/transaction/i, "receipt-text"], [/drug interaction/i, "git-compare-arrows"],
        [/allerg/i, "shield-alert"], [/dosage/i, "gauge"], [/clinical review|decision support/i, "shield-check"],
        [/explainable|ai priority/i, "brain-circuit"], [/governance|rule management/i, "shield-check"],
        [/report/i, "chart-column"], [/staff/i, "users"], [/pharmacy profile|pharmacy information/i, "building-2"],
        [/administrator/i, "user-cog"], [/audit/i, "history"]
    ];

    function iconFor(text) {
        const value = (text || "").replace(/\s+/g, " ").trim();
        const match = iconRules.find(([pattern]) => pattern.test(value));
        return match ? match[1] : null;
    }

    function prependIcon(element, name, className) {
        if (!name || element.querySelector(":scope > [data-lucide]")) return;
        const icon = document.createElement("i");
        icon.dataset.lucide = name;
        icon.className = `icon ${className}`;
        icon.setAttribute("aria-hidden", "true");
        element.prepend(icon);
    }

    function enhanceApplicationIcons() {
        const content = document.querySelector("main, .main-content, .public-page");
        if (!content) return;

        content.querySelectorAll(".btn, button[type='submit']").forEach((element) => {
            prependIcon(element, iconFor(element.textContent), "button-icon");
        });
        content.querySelectorAll("h1, h2.section-title, .card-title, fieldset > legend").forEach((element) => {
            const icon = iconFor(element.textContent);
            if (icon) {
                element.classList.add("heading-with-icon");
                prependIcon(element, icon, "section-icon");
            }
        });
        content.querySelectorAll(".public-card h3").forEach((heading) => {
            if (heading.closest(".public-card").querySelector(".public-card-icon [data-lucide]")) return;
            prependIcon(heading, iconFor(heading.textContent), "feature-icon");
            if (heading.querySelector(":scope > [data-lucide]")) heading.classList.add("heading-with-icon");
        });
        content.querySelectorAll(".empty-state").forEach((element) => {
            prependIcon(element, iconFor(element.textContent) || "inbox", "icon-lg");
        });
        content.querySelectorAll(".badge").forEach((element) => {
            const text = element.textContent.trim();
            const name = /active|passed|complete|approved/i.test(text) ? "circle-check" :
                /warning|review/i.test(text) ? "triangle-alert" :
                /inactive|retired/i.test(text) ? "circle-x" : null;
            prependIcon(element, name, "status-icon");
        });
    }

    function initializeLucideIcons() {
        if (!window.lucide || typeof window.lucide.createIcons !== "function") {
            return;
        }

        enhanceApplicationIcons();

        window.lucide.createIcons({
            attrs: {
                "aria-hidden": "true",
                focusable: "false"
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initializeLucideIcons);
    } else {
        initializeLucideIcons();
    }
})();
