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

    // 公开接口
    window.Tasks = {
        pollTask: pollTask,
        uploadWithProgress: uploadWithProgress,
        submitAjaxTask: submitAjaxTask,
        submitAjaxDirect: submitAjaxDirect,
        setProgress: setProgress,
        setMessage: setMessage,
    };
})(window);
