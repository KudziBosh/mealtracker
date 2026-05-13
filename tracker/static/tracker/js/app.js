/*
 * Dashboard interaction glue: segmented log-form toggle, food combobox,
 * toast auto-dismiss, and the mobile FAB focus jump.
 *
 * Kept in a single file (no module split, no bundler) to match the project's
 * "minimal JS, server-rendered" stance from CLAUDE.md. Everything is scoped
 * to elements that opt in via `data-*` attributes — no globals beyond the
 * `MT` namespace, no implicit page-wide side effects.
 */
(function () {
    "use strict";

    // -------------------------------------------------------------------
    // Segmented "Recipe / Single food" toggle in the meals panel.
    // The HTML ships with `style="display:none"` on the inactive form so a
    // no-JS page still renders sensibly with only the recipe form visible.
    // -------------------------------------------------------------------
    function activateLogTab(toggle, name) {
        toggle.dataset.active = name;
        toggle.querySelectorAll("[data-log-tab]").forEach(function (btn) {
            const isActive = btn.dataset.logTab === name;
            btn.dataset.active = isActive ? "true" : "false";
            btn.setAttribute("aria-selected", isActive ? "true" : "false");
        });
        toggle.querySelectorAll("[data-log-form]").forEach(function (form) {
            form.style.display = form.dataset.logForm === name ? "" : "none";
        });
        // If the user just switched to the food form, focus the search input
        // so the next keystroke starts filtering immediately.
        if (name === "food") {
            const input = toggle.querySelector("[data-food-search-input]");
            if (input) {
                // RAF so the just-shown form has laid out before we focus.
                window.requestAnimationFrame(function () {
                    input.focus();
                });
            }
        }
    }

    function initLogToggles(root) {
        root.querySelectorAll("[data-log-toggle]").forEach(function (toggle) {
            // Wire tab clicks once.
            if (toggle.dataset.bound === "1") return;
            toggle.dataset.bound = "1";
            toggle.addEventListener("click", function (event) {
                const tab = event.target.closest("[data-log-tab]");
                if (!tab || !toggle.contains(tab)) return;
                activateLogTab(toggle, tab.dataset.logTab);
            });
            // Set initial state from data-active.
            activateLogTab(toggle, toggle.dataset.active || "recipe");
        });
    }

    // -------------------------------------------------------------------
    // Food combobox — the search input swaps in a fresh result list via
    // HTMX, this handler converts a row click into "select that food".
    // -------------------------------------------------------------------
    function initFoodComboboxes(root) {
        root.querySelectorAll("[data-food-combobox]").forEach(function (combo) {
            if (combo.dataset.bound === "1") return;
            combo.dataset.bound = "1";

            const input = combo.querySelector("[data-food-search-input]");
            const hiddenId = combo.querySelector("[data-food-id-input]");
            const gramsInput = combo.querySelector("[data-grams-input]");

            // Click / keyboard-select on a result.
            combo.addEventListener("click", function (event) {
                const option = event.target.closest("[data-food-id]");
                if (!option) return;
                selectFood(option);
            });
            combo.addEventListener("keydown", function (event) {
                const option = event.target.closest("[data-food-id]");
                if (option && (event.key === "Enter" || event.key === " ")) {
                    event.preventDefault();
                    selectFood(option);
                }
            });

            // Clear the hidden id when the user edits the search text again,
            // so a half-edited label doesn't silently submit a stale food.
            if (input) {
                input.addEventListener("input", function () {
                    if (hiddenId) hiddenId.value = "";
                    input.setAttribute("aria-expanded", "true");
                });
                input.addEventListener("focus", function () {
                    input.setAttribute("aria-expanded", "true");
                });
            }

            // Click-away closes the dropdown without clearing the selection.
            document.addEventListener("click", function (event) {
                if (!combo.contains(event.target)) {
                    const list = combo.querySelector("#food-search-results");
                    if (list) list.classList.add("hidden");
                    if (input) input.setAttribute("aria-expanded", "false");
                }
            });

            function selectFood(option) {
                if (!input || !hiddenId) return;
                input.value = option.dataset.foodName || "";
                hiddenId.value = option.dataset.foodId || "";
                input.setAttribute("aria-expanded", "false");

                // Prefill grams with the food's default — only if the user
                // hasn't already typed something there.
                const fallback = option.dataset.defaultGrams || "";
                if (gramsInput && !gramsInput.value && fallback) {
                    gramsInput.value = fallback;
                }
                const list = combo.querySelector("#food-search-results");
                if (list) list.classList.add("hidden");
                // Focus grams so the user can adjust the amount or hit Add.
                if (gramsInput) gramsInput.focus();
            }
        });
    }

    // After HTMX swaps the dropdown content, re-show it (server-rendered HTML
    // controls its own visibility — but we want the list visible once results
    // arrived from a search keystroke).
    document.addEventListener("htmx:afterSwap", function (event) {
        if (event.detail && event.detail.target && event.detail.target.id === "food-search-results") {
            event.detail.target.classList.remove("hidden");
        }
        // Re-init any newly-swapped meals panel so freshly-rendered combobox
        // / toggle markup wires up automatically.
        initLogToggles(document);
        initFoodComboboxes(document);
    });

    // -------------------------------------------------------------------
    // Toast auto-dismiss + manual close button.
    // The OOB swap replaces #toast-area in one shot; we just attach a timer
    // and a click handler to whatever lands inside.
    // -------------------------------------------------------------------
    function initToasts() {
        document.querySelectorAll("[data-toast]").forEach(function (toast) {
            if (toast.dataset.bound === "1") return;
            toast.dataset.bound = "1";

            const dismiss = function () {
                toast.style.transition = "opacity 200ms ease, transform 200ms ease";
                toast.style.opacity = "0";
                toast.style.transform = "translate(-50%, 0.5rem)";
                window.setTimeout(function () {
                    toast.remove();
                }, 220);
            };

            // Manual close.
            toast.querySelectorAll("[data-toast-dismiss]").forEach(function (btn) {
                btn.addEventListener("click", dismiss);
            });

            // Auto-dismiss after 6s — long enough for "Undo" reflexes,
            // short enough not to linger over the next interaction.
            window.setTimeout(dismiss, 6000);
        });
    }

    document.addEventListener("htmx:afterSwap", initToasts);

    // -------------------------------------------------------------------
    // FAB: scrolling is handled by the href="#meal-log-anchor", we just
    // also flip the segmented toggle to "food" and focus the search input
    // so the next tap is keying in a food name.
    // -------------------------------------------------------------------
    function initQuickLogFab(root) {
        const fab = root.querySelector("[data-quick-log-fab]");
        if (!fab || fab.dataset.bound === "1") return;
        fab.dataset.bound = "1";
        fab.addEventListener("click", function () {
            const toggle = document.querySelector("[data-log-toggle]");
            if (toggle) activateLogTab(toggle, "food");
            // The hash will smooth-scroll via CSS; defer focus so the
            // scroll has started before we steal focus to the input.
            window.setTimeout(function () {
                const input = document.querySelector("[data-food-search-input]");
                if (input) input.focus();
            }, 200);
        });
    }

    // -------------------------------------------------------------------
    // Boot.
    // -------------------------------------------------------------------
    function init() {
        initLogToggles(document);
        initFoodComboboxes(document);
        initToasts();
        initQuickLogFab(document);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
