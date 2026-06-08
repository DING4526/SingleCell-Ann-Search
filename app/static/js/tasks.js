/**
 * tasks.js - 通用 AJAX 任务工具库
 * 提供：submitAjaxForm / pollTask / uploadWithProgress
 */

(function (window) {
    "use strict";

    /**
     * 显示进度条
     * @param {HTMLElement} progressBar - .progress-bar 元素
     * @param {number} value - 0-100
     */
    function setProgress(progressBar, value) {
        if (!progressBar) return;
        const pct = Math.max(0, Math.min(100, value));
        progressBar.style.width = pct + "%";
        progressBar.setAttribute("aria-valuenow", pct);
        progressBar.textContent = pct + "%";
    }

    /**
     * 显示消息框
     * @param {HTMLElement} messageBox
     * @param {string} msg
     * @param {'info'|'success'|'danger'|'warning'} type
     */
    function setMessage(messageBox, msg, type) {
        if (!messageBox) return;
        messageBox.className = "alert alert-" + (type || "info") + " mt-2";
        messageBox.textContent = msg;
        messageBox.style.display = msg ? "block" : "none";
    }

    /**
     * 轮询任务状态，直到 success 或 error
     * @param {number} taskId
     * @param {Object} opts
     * @param {HTMLElement} [opts.progressBar]
     * @param {HTMLElement} [opts.messageBox]
     * @param {Function} [opts.onSuccess]  回调：(taskResult) => void
     * @param {Function} [opts.onError]    回调：(errorMsg) => void
     * @param {number}   [opts.interval]   轮询间隔毫秒，默认 1000
     */
    function pollTask(taskId, opts) {
        opts = opts || {};
        var interval = opts.interval || 1000;
        var timeoutHandle;

        function poll() {
            fetch("/api/tasks/" + taskId, { credentials: "same-origin" })
                .then(function (resp) { return resp.json(); })
                .then(function (data) {
                    if (!data.ok) {
                        clearTimeout(timeoutHandle);
                        setMessage(opts.messageBox, data.message || "任务查询失败", "danger");
                        if (opts.onError) opts.onError(data.message);
                        return;
                    }

                    setProgress(opts.progressBar, data.progress || 0);
                    setMessage(opts.messageBox, data.message || "", "info");

                    if (data.status === "success") {
                        setProgress(opts.progressBar, 100);
                        setMessage(opts.messageBox, data.message || "操作成功！", "success");
                        if (opts.onSuccess) opts.onSuccess(data);
                    } else if (data.status === "error") {
                        setMessage(opts.messageBox, (data.error || data.message || "任务执行失败"), "danger");
                        if (opts.onError) opts.onError(data.error || data.message);
                    } else {
                        // pending / running → 继续轮询
                        timeoutHandle = setTimeout(poll, interval);
                    }
                })
                .catch(function (err) {
                    setMessage(opts.messageBox, "网络错误，轮询中断。", "danger");
                    if (opts.onError) opts.onError(String(err));
                });
        }

        poll();
    }

    /**
     * 使用 XMLHttpRequest 带进度上传（适用于大文件上传表单）
     * @param {HTMLFormElement} form
     * @param {Object} opts
     * @param {HTMLElement} [opts.progressBar]   上传进度条 .progress-bar 元素
     * @param {HTMLElement} [opts.messageBox]
     * @param {HTMLButtonElement} [opts.submitBtn]
     * @param {Function} [opts.onSuccess]  回调：(responseJSON) => void
     * @param {Function} [opts.onError]    回调：(msg) => void
     */
    function uploadWithProgress(form, opts) {
        opts = opts || {};
        var btn = opts.submitBtn || form.querySelector('[type="submit"]');

        if (btn) { btn.disabled = true; }
        setMessage(opts.messageBox, "正在上传文件...", "info");
        setProgress(opts.progressBar, 0);

        var xhr = new XMLHttpRequest();
        var formData = new FormData(form);

        xhr.upload.onprogress = function (e) {
            if (e.lengthComputable) {
                var pct = Math.round((e.loaded / e.total) * 100);
                setProgress(opts.progressBar, pct);
                setMessage(opts.messageBox, "上传中... " + pct + "%", "info");
            }
        };

        xhr.onload = function () {
            if (btn) { btn.disabled = false; }
            try {
                var data = JSON.parse(xhr.responseText);
                if (data.ok) {
                    setProgress(opts.progressBar, 100);
                    setMessage(opts.messageBox, data.message || "上传成功！", "success");
                    if (opts.onSuccess) opts.onSuccess(data);
                } else {
                    setMessage(opts.messageBox, data.message || "上传失败。", "danger");
                    if (opts.onError) opts.onError(data.message);
                }
            } catch (ex) {
                setMessage(opts.messageBox, "服务器响应异常。", "danger");
                if (opts.onError) opts.onError("JSON 解析失败");
            }
        };

        xhr.onerror = function () {
            if (btn) { btn.disabled = false; }
            setMessage(opts.messageBox, "网络错误，上传失败。", "danger");
            if (opts.onError) opts.onError("XMLHttpRequest error");
        };

        xhr.open("POST", form.action || form.getAttribute("data-url") || "/api/datasets/upload");
        xhr.send(formData);
    }

    /**
     * 提交 AJAX 表单（非文件上传，发起后台任务，然后轮询）
     * @param {HTMLFormElement} form
     * @param {Object} opts
     * @param {string} [opts.url]           覆盖 form.action
     * @param {HTMLElement} [opts.progressBar]
     * @param {HTMLElement} [opts.messageBox]
     * @param {HTMLButtonElement} [opts.submitBtn]
     * @param {Function} [opts.onSuccess]
     * @param {Function} [opts.onError]
     * @param {number}   [opts.pollInterval]
     */
    function submitAjaxTask(form, opts) {
        opts = opts || {};
        var btn = opts.submitBtn || form.querySelector('[type="submit"]');
        var url = opts.url || form.action;

        if (btn) { btn.disabled = true; }
        setMessage(opts.messageBox, "正在提交任务...", "info");
        setProgress(opts.progressBar, 0);

        var formData = new FormData(form);

        fetch(url, {
            method: "POST",
            body: formData,
            credentials: "same-origin",
        })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                if (!data.ok) {
                    if (btn) { btn.disabled = false; }
                    setMessage(opts.messageBox, data.message || "提交失败。", "danger");
                    if (opts.onError) opts.onError(data.message);
                    return;
                }
                setMessage(opts.messageBox, "任务已提交，正在处理...", "info");
                setProgress(opts.progressBar, 5);

                pollTask(data.task_id, {
                    progressBar: opts.progressBar,
                    messageBox: opts.messageBox,
                    interval: opts.pollInterval || 1000,
                    onSuccess: function (taskData) {
                        if (btn) { btn.disabled = false; }
                        if (opts.onSuccess) opts.onSuccess(taskData);
                    },
                    onError: function (msg) {
                        if (btn) { btn.disabled = false; }
                        if (opts.onError) opts.onError(msg);
                    },
                });
            })
            .catch(function (err) {
                if (btn) { btn.disabled = false; }
                setMessage(opts.messageBox, "网络错误：" + String(err), "danger");
                if (opts.onError) opts.onError(String(err));
            });
    }

    /**
     * 直接 AJAX POST（无任务轮询，直接拿结果）
     * @param {HTMLFormElement} form
     * @param {Object} opts
     * @param {string} [opts.url]
     * @param {HTMLElement} [opts.messageBox]
     * @param {HTMLButtonElement} [opts.submitBtn]
     * @param {Function} [opts.onSuccess]
     * @param {Function} [opts.onError]
     */
    function submitAjaxDirect(form, opts) {
        opts = opts || {};
        var btn = opts.submitBtn || form.querySelector('[type="submit"]');
        var url = opts.url || form.action;

        if (btn) { btn.disabled = true; }
        setMessage(opts.messageBox, "正在执行，请稍候...", "info");

        fetch(url, {
            method: "POST",
            body: new FormData(form),
            credentials: "same-origin",
        })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                if (btn) { btn.disabled = false; }
                if (data.ok) {
                    setMessage(opts.messageBox, "操作完成。", "success");
                    if (opts.onSuccess) opts.onSuccess(data);
                } else {
                    setMessage(opts.messageBox, data.message || "操作失败。", "danger");
                    if (opts.onError) opts.onError(data.message);
                }
            })
            .catch(function (err) {
                if (btn) { btn.disabled = false; }
                setMessage(opts.messageBox, "网络错误：" + String(err), "danger");
                if (opts.onError) opts.onError(String(err));
            });
    }

    /**
     * 全局任务指示器：轮询 /api/tasks/active，更新导航栏徽标
     * 支持自适应间隔：有活跃任务时快速轮询，空闲时降频
     * @param {number} [interval=15000] 空闲轮询间隔毫秒
     * @param {number} [activeInterval=500] 活跃轮询间隔毫秒
     */
    function pollActiveTasks(interval, activeInterval) {
        interval = interval || 15000;
        activeInterval = activeInterval || 500;
        var wrap = document.getElementById("globalTaskWrap");
        var badge = document.getElementById("globalTaskCount");
        if (!wrap || !badge) return;

        var timerHandle = null;
        var lastActiveCount = 0;

        function scheduleNext(delay) {
            clearTimeout(timerHandle);
            timerHandle = setTimeout(update, delay);
        }

        function update() {
            fetch("/api/tasks/active", { credentials: "same-origin" })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.ok) { scheduleNext(interval); return; }
                    var count = data.tasks ? data.tasks.length : 0;
                    if (count > 0) {
                        badge.textContent = count;
                        wrap.style.display = "";
                    } else {
                        wrap.style.display = "none";
                    }

                    // 自适应：活跃时快速轮询，空闲时降频
                    var hadActive = lastActiveCount > 0;
                    lastActiveCount = count;
                    if (count > 0) {
                        scheduleNext(activeInterval);
                    } else {
                        // 从活跃变空闲时，通知页面刷新（如果回调存在）
                        if (hadActive && window._onWorkbenchIdle) {
                            window._onWorkbenchIdle();
                        }
                        scheduleNext(interval);
                    }
                })
                .catch(function () { scheduleNext(interval); });
        }

        update();
    }

    // 公开接口
    window.Tasks = {
        pollTask: pollTask,
        uploadWithProgress: uploadWithProgress,
        submitAjaxTask: submitAjaxTask,
        submitAjaxDirect: submitAjaxDirect,
        setProgress: setProgress,
        setMessage: setMessage,
        pollActiveTasks: pollActiveTasks,
        showToast: showToast,
    };

    // ===== Toast 通知（6.2a） =====
    var MAX_TOASTS = 3;

    function showToast(opts) {
        opts = opts || {};
        var container = document.getElementById("globalToastContainer");
        if (!container) return;

        /* 限制最大数量 */
        while (container.children.length >= MAX_TOASTS) {
            container.removeChild(container.firstChild);
        }

        var typeColors = {
            success: { bg: "rgba(34,197,94,0.18)", border: "rgba(34,197,94,0.5)", icon: "&#10003;" },
            error: { bg: "rgba(239,68,68,0.18)", border: "rgba(239,68,68,0.5)", icon: "&#10007;" },
            info: { bg: "rgba(56,189,248,0.18)", border: "rgba(56,189,248,0.5)", icon: "&#8505;" },
        };
        var tc = typeColors[opts.type] || typeColors.info;

        var toastEl = document.createElement("div");
        toastEl.className = "toast app-toast";
        toastEl.setAttribute("role", "alert");
        toastEl.setAttribute("aria-live", "assertive");
        toastEl.setAttribute("aria-atomic", "true");
        toastEl.style.cssText = "background:" + tc.bg + ";border:1px solid " + tc.border + ";";

        var actionHtml = "";
        if (opts.actionUrl && opts.actionLabel) {
            actionHtml = '<a href="' + opts.actionUrl + '" class="btn btn-sm btn-outline-primary mt-1">' + opts.actionLabel + '</a>';
        }

        toastEl.innerHTML =
            '<div class="toast-header" style="background:transparent;border-bottom:1px solid ' + tc.border + ';">' +
            '<span class="me-auto fw-bold" style="font-size:0.9rem;">' + tc.icon + ' ' + (opts.title || "通知") + '</span>' +
            '<button type="button" class="btn-close btn-close-sm" data-bs-dismiss="toast"></button>' +
            '</div>' +
            '<div class="toast-body" style="font-size:0.85rem;">' +
            '<div>' + (opts.message || "") + '</div>' +
            actionHtml +
            '</div>';

        container.appendChild(toastEl);
        var bsToast = new bootstrap.Toast(toastEl, { delay: 5000 });
        bsToast.show();
        toastEl.addEventListener("hidden.bs.toast", function () { toastEl.remove(); });
    }

    // ===== GlobalTaskTracker 单例（6.3a） =====
    var GlobalTaskTracker = {
        _timer: null,
        _lastActiveCount: 0,
        _subscribers: [],
        _idleInterval: 15000,
        _activeInterval: 2000,
        _paused: false,

        start: function (idleInterval, activeInterval) {
            this._idleInterval = idleInterval || 15000;
            this._activeInterval = activeInterval || 2000;
            var self = this;

            /* visibility-aware polling（6.3b） */
            document.addEventListener("visibilitychange", function () {
                if (document.hidden) {
                    self._paused = true;
                    clearTimeout(self._timer);
                } else {
                    self._paused = false;
                    self._update();
                }
            });

            this._update();
        },

        stop: function () {
            clearTimeout(this._timer);
            this._timer = null;
        },

        subscribe: function (callbacks) {
            this._subscribers.push(callbacks);
            var self = this;
            return function () {
                self._subscribers = self._subscribers.filter(function (s) { return s !== callbacks; });
            };
        },

        _scheduleNext: function (delay) {
            var self = this;
            clearTimeout(this._timer);
            this._timer = setTimeout(function () { self._update(); }, delay);
        },

        _update: function () {
            if (this._paused) return;
            var self = this;
            var wrap = document.getElementById("globalTaskWrap");
            var badge = document.getElementById("globalTaskCount");

            fetch("/api/tasks/active", { credentials: "same-origin" })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.ok) { self._scheduleNext(self._idleInterval); return; }
                    var count = data.tasks ? data.tasks.length : 0;

                    /* 更新导航栏徽标 */
                    if (wrap && badge) {
                        if (count > 0) { badge.textContent = count; wrap.style.display = ""; }
                        else { wrap.style.display = "none"; }
                    }

                    /* 任务完成转换检测 */
                    var hadActive = self._lastActiveCount > 0;
                    self._lastActiveCount = count;

                    if (hadActive && count === 0) {
                        /* 从活跃→空闲，通知所有订阅者 */
                        self._subscribers.forEach(function (cb) {
                            if (cb.onActiveChange) cb.onActiveChange(false, count);
                            if (cb.onTaskComplete) cb.onTaskComplete();
                        });
                        /* 工作台回调 */
                        if (window._onWorkbenchIdle) window._onWorkbenchIdle();
                        /* Toast 通知 */
                        showToast({ title: "任务完成", message: "后台任务已全部完成。", type: "success" });
                    } else if (hadActive && count > 0) {
                        self._subscribers.forEach(function (cb) {
                            if (cb.onActiveChange) cb.onActiveChange(true, count);
                        });
                    }

                    self._scheduleNext(count > 0 ? self._activeInterval : self._idleInterval);
                })
                .catch(function () { self._scheduleNext(self._idleInterval); });
        },
    };

    window.GlobalTaskTracker = GlobalTaskTracker;

    // ===== 可折叠 Level 3 初始化（7.1c） =====
    function initCollapsibleLevel3() {
        var hints = document.querySelectorAll(".collapsible-hint");
        hints.forEach(function (el) {
            var targetSel = el.getAttribute("data-bs-target");
            if (!targetSel) return;
            var target = document.querySelector(targetSel);
            if (!target) return;
            el.addEventListener("click", function () {
                var isExpanded = el.getAttribute("aria-expanded") === "true";
                el.setAttribute("aria-expanded", String(!isExpanded));
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initCollapsibleLevel3);
    } else {
        initCollapsibleLevel3();
    }
})(window);
