/** EasyConnect - Enhanced Mobile Controller */
(function () {
  let ws = null;
  let sessionToken = localStorage.getItem("easyconnect_session_token") || localStorage.getItem("pulse_session_token");
  let pcDeviceName = "Windows PC";
  let isConnected = false;
  let sensitivity = parseFloat(localStorage.getItem("pulse_sens") || "1.0");
  let activeTab = "trackpad";
  
  // Screen & Camera & Window State
  let isScreenStreaming = false;
  let isWebcamStreaming = false;
  let isWindowStreaming = false;
  let activeWindowHwnd = null;
  let cachedAppWindows = [];
  let monitorsList = [];
  let selectedMonitorId = 1;
  let isFindPcRinging = false;
  let statsInterval = null;
  let reconnectAttempts = 0;
  let currentBrowsePath = "";

  // Custom Remotes State
  let customButtons = JSON.parse(localStorage.getItem("pulse_custom_buttons") || "[]");
  if (customButtons.length === 0) {
    customButtons = [
      { id: "1", name: "VS Code", icon: "💻", type: "app", target: "vscode" },
      { id: "2", name: "Chrome", icon: "🌐", type: "app", target: "chrome" },
      { id: "3", name: "Explorer", icon: "📁", type: "app", target: "explorer" },
      { id: "4", name: "Lock PC", icon: "🔒", type: "action", target: "lock" },
    ];
  }

  function vibrate(ms = 15) {
    if (navigator.vibrate) {
      try { navigator.vibrate(ms); } catch (e) {}
    }
  }

  function showToast(msg, type = "info") {
    let container = document.getElementById("toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "toast-container";
      container.className = "toast-container";
      document.body.appendChild(container);
    }
    const toast = document.createElement("div");
    toast.className = `toast-item toast-${type}`;
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => {
      toast.classList.add("toast-fadeout");
      setTimeout(() => toast.remove(), 350);
    }, 2800);
  }

  const pairingScreen = document.getElementById("pairing-screen");
  const appContainer = document.getElementById("app-container");
  const pairStatusBox = document.getElementById("pair-status-box");
  const pairSpinner = document.getElementById("pair-spinner");
  const pairStatusText = document.getElementById("pair-status-text");
  const connectedPcName = document.getElementById("connected-pc-name");
  const latencyBadge = document.getElementById("latency-badge");
  const manualPairBox = document.getElementById("manual-pair-box");
  const manualTokenInput = document.getElementById("manual-token-input");
  const manualPairBtn = document.getElementById("manual-pair-btn");
  const manualPairBtnText = document.getElementById("manual-pair-btn-text");
  const manualPairSpinner = document.getElementById("manual-pair-spinner");

  function clearAllSessions() {
    localStorage.removeItem("easyconnect_session_token");
    localStorage.removeItem("pulse_session_token");
    sessionToken = null;
  }

  function setPairingState(state, message = "") {
    if (pairStatusText) {
      pairStatusText.textContent = message || "";
      pairStatusText.style.color = state === "error" ? "var(--red)" : "var(--text-muted)";
    }
    if (pairSpinner) {
      pairSpinner.style.display = state === "loading" ? "inline-block" : "none";
    }
    if (manualPairSpinner) {
      manualPairSpinner.style.display = state === "loading" ? "inline-block" : "none";
    }
    if (manualPairBtn) {
      manualPairBtn.disabled = state === "loading";
    }
    if (manualPairBtnText) {
      manualPairBtnText.textContent = state === "loading" ? "Connecting..." : "Connect to PC";
    }
    if (manualPairBox) {
      manualPairBox.style.display = state === "connected" ? "none" : "block";
    }
  }

  window.addEventListener("DOMContentLoaded", () => {
    setupMainTabs();
    setupSubPills();
    setupTrackpad();
    setupKeysAndShortcuts();
    setupScreenViewer();
    setupWebcam();
    setupAppWindowsMonitor();
    setupMediaControls();
    setupFileManager();
    setupClipboard();
    setupDashboard();
    setupCustomButtons();
    setupEmergencyLock();
    setupBossKey();
    setupBrightnessControl();
    setupSecurityControls();
    setupLiveHUDLoop();
    setupAutoUpdater();
    setupMediaServer();
    setupVoiceAssistant();

    const urlParams = new URLSearchParams(window.location.search);
    const pairToken = urlParams.get("pair");
    const isLoopback = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";

    if (pairToken) {
      setPairingState("loading", "Validating pairing token...");
      performPairing(pairToken);
    } else if (sessionToken) {
      setPairingState("loading", "Connecting to PC session...");
      
      if (window._authWatchdog) clearTimeout(window._authWatchdog);
      window._authWatchdog = setTimeout(() => {
        if (!isConnected) {
          console.warn("[Auth] Session connection watchdog triggered. Prompting PIN.");
          clearAllSessions();
          try { if (ws) ws.close(); } catch (e) {}
          setPairingState("idle", "PC restarted or session expired. Enter 6-digit PIN:");
          manualTokenInput?.focus();
        }
      }, 3500);

      connectWebSocket();
    } else if (isLoopback) {
      setPairingState("loading", "Connecting to local PC...");
      performPairing("local");
    } else {
      setPairingState("idle", "Scan QR code or enter 6-digit PIN from PC:");
      manualTokenInput?.focus();
    }

    manualPairBtn?.addEventListener("click", () => {
      const manualToken = manualTokenInput?.value.trim();
      if (manualToken) performPairing(manualToken);
    });

    manualTokenInput?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        const manualToken = manualTokenInput?.value.trim();
        if (manualToken) performPairing(manualToken);
      }
    });

    manualTokenInput?.addEventListener("input", (e) => {
      const digits = e.target.value.replace(/\D/g, "");
      e.target.value = digits;
      if (digits.length === 6) {
        performPairing(digits);
      }
    });
  });

  async function performPairing(token) {
    if (!token) return;
    setPairingState("loading", "Connecting to PC...");
    try {
      const res = await fetch("/api/pair", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pairing_token: token,
          device_id: "phone-" + Math.random().toString(36).substring(2, 8),
          name: navigator.userAgent.includes("iPhone") ? "iPhone" : (navigator.userAgent.includes("Android") ? "Android Phone" : "Mobile Client")
        })
      });
      const data = await res.json();
      if (data.success && data.session_token) {
        sessionToken = data.session_token;
        localStorage.setItem("pulse_session_token", sessionToken);
        localStorage.setItem("easyconnect_session_token", sessionToken);
        pcDeviceName = data.device_name || "Windows PC";
        window.history.replaceState({}, document.title, window.location.pathname);
        setPairingState("loading", "Authenticating stream...");
        connectWebSocket();
      } else {
        clearAllSessions();
        setPairingState("error", data.error || "Pairing token expired or invalid.");
        manualTokenInput?.focus();
      }
    } catch (err) {
      clearAllSessions();
      setPairingState("error", "Unable to connect. Ensure phone is on the same Wi-Fi as PC.");
      manualTokenInput?.focus();
    }
  }

  function showPairError(msg) {
    clearAllSessions();
    setPairingState("error", msg);
  }

  function connectWebSocket() {
    if (ws && ws.readyState === WebSocket.OPEN) {
      try { ws.close(); } catch (e) {}
    }
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      reconnectAttempts = 0;
      ws.send(JSON.stringify({ event: "auth", data: { session_token: sessionToken } }));
      startProximityPing();
    };

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        handleServerMessage(msg);
      } catch (err) {}
    };

    ws.onclose = () => {
      isConnected = false;
      if (proximityPingInterval) {
        clearInterval(proximityPingInterval);
        proximityPingInterval = null;
      }
      if (!sessionToken) return;

      reconnectAttempts++;
      if (reconnectAttempts > 3) {
        clearAllSessions();
        pairingScreen.classList.remove("hidden");
        appContainer.classList.add("hidden");
        setPairingState("error", "PC unreachable or agent restarted. Enter 6-digit PIN:");
        manualTokenInput?.focus();
        return;
      }

      latencyBadge.textContent = `Reconnecting (${reconnectAttempts})...`;
      setTimeout(() => {
        if (sessionToken) connectWebSocket();
      }, Math.min(3000, 1000 * reconnectAttempts));
    };

    ws.onerror = () => { ws.close(); };
  }

  let proximityPingInterval = null;
  function startProximityPing() {
    if (proximityPingInterval) clearInterval(proximityPingInterval);
    proximityPingInterval = setInterval(() => {
      if (isConnected && ws && ws.readyState === WebSocket.OPEN) {
        sendWS("ping:proximity");
      }
    }, 3000);
  }

  window.addEventListener("pagehide", () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      try { ws.close(); } catch (e) {}
    }
  });
  window.addEventListener("beforeunload", () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      try { ws.close(); } catch (e) {}
    }
  });

  function sendWS(event, data = {}) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ event, data }));
    }
  }
  function handleServerMessage(msg) {
    const { event, data } = msg;

    if (event === "auth_success") {
      if (window._authWatchdog) {
        clearTimeout(window._authWatchdog);
        window._authWatchdog = null;
      }
      isConnected = true;
      reconnectAttempts = 0;
      pairingScreen.classList.add("hidden");
      appContainer.classList.remove("hidden");
      setPairingState("connected");
      pcDeviceName = data.device_name || "Windows PC";
      connectedPcName.textContent = pcDeviceName;
      latencyBadge.textContent = "🟢 Direct Wi-Fi";

      sendWS("monitors:list");
      sendWS("app:list");
      sendWS("custom_remotes:get");
      sendWS("sentry:get_status");
      if (activeTab === "files") fetchFileList();
      if (activeTab === "system") refreshSystemData();
      if (activeTab === "security") sendWS("security:logs");
    } else if (event === "auth_error") {
      if (window._authWatchdog) {
        clearTimeout(window._authWatchdog);
        window._authWatchdog = null;
      }
      clearAllSessions();
      pairingScreen.classList.remove("hidden");
      appContainer.classList.add("hidden");
      setPairingState("error", "Session expired. Enter 6-digit PIN from PC:");
      manualTokenInput?.focus();
    } else if (event === "permission_denied") {
      alert(`⚠️ ${data.message}`);
    } else if (event === "screen:frame_data") {
      renderScreenFrame(data.frame);
    } else if (event === "webrtc:answer") {
      if (window.handleWebRTCAnswer) window.handleWebRTCAnswer(data);
    } else if (event === "webrtc:error") {
      if (window.handleWebRTCError) window.handleWebRTCError(data);
    } else if (event === "webcam:frame_data") {
      renderWebcamFrame(data.frame);
    } else if (event === "monitors:list_data") {
      renderMonitors(data.monitors);
    } else if (event === "app:list_data") {
      renderQuickActions(data.apps);
    } else if (event === "app:launch_result") {
      vibrate(20);
      alert(data.message);
    } else if (event === "find_pc:status") {
      updateFindPcStatus(data.success, data.message);
    } else if (event === "clipboard:data") {
      document.getElementById("clip-pc-text").value = data.text || "";
      renderClipboardHistory(data.history || []);
    } else if (event === "clipboard:updated") {
      vibrate(15);
      alert("✅ Text copied to PC Clipboard!");
    } else if (event === "clipboard:cleared") {
      vibrate(15);
      document.getElementById("clip-pc-text").value = "";
      alert("PC Clipboard cleared.");
    } else if (event === "system:stats_data") {
      renderSystemStats(data);
    } else if (event === "system:action_result") {
      vibrate(30);
      showToast(data.message, data.success ? "success" : "error");
    } else if (event === "system:panic_result") {
      vibrate([50, 50, 100]);
      showToast(data.message, "error");
    } else if (event === "brightness:changed") {
      updateBrightnessUI(data.level);
    } else if (event === "system:update_info") {
      if (window.renderUpdateBanner) window.renderUpdateBanner(data);
    } else if (event === "system:update_result") {
      vibrate(25);
      showToast(data.message, data.success ? "success" : "error");
    } else if (event === "security:settings") {
      if (data.guard_active !== undefined) {
        const chk = document.getElementById("toggle-cctv-guard");
        if (chk) chk.checked = !!data.guard_active;
      }
      if (data.walkaway_enabled !== undefined) {
        const chk = document.getElementById("toggle-walkaway-lock");
        if (chk) chk.checked = !!data.walkaway_enabled;
      }
      if (data.sentry) updateSentryUI(data.sentry);
      if (data.last_intruder && data.last_intruder.photo) {
        updateIntruderPreview(data.last_intruder);
      }
    } else if (event === "guard:status") {
      vibrate(20);
      showToast(data.message, data.active ? "success" : "info");
      const chk = document.getElementById("toggle-cctv-guard");
      if (chk) chk.checked = !!data.active;
    } else if (event === "guard:intruder_alert") {
      handleIntruderAlert(data);
    } else if (event === "settings:walkaway_status") {
      vibrate(15);
      showToast(`Walk-Away Auto-Lock ${data.enabled ? "Enabled" : "Disabled"}`, "info");
      const chk = document.getElementById("toggle-walkaway-lock");
      if (chk) chk.checked = !!data.enabled;
    } else if (event === "sentry:status") {
      updateSentryUI(data);
    } else if (event === "sentry:triggered") {
      handleSentryTriggered(data);
    } else if (event === "security:logs_data") {
      renderSecurityLogs(data.logs || []);
    } else if (event === "files:list_data") {
      renderFileList(data);
    } else if (event === "devices:list_data") {
      renderPairedDevices(data.devices);
    } else if (event === "devices:perms_updated") {
      vibrate(15);
      alert("Permissions updated!");
    } else if (event === "devices:revoked") {
      vibrate(20);
      sendWS("devices:list");
    } else if (event === "devices:all_revoked") {
      alert("All devices disconnected.");
      window.location.reload();
    } else if (event === "windows:list_data" || event === "windows:thumbnails_data") {
      renderAppWindows(data.windows || []);
    } else if (event === "windows:frame_data") {
      renderWindowStreamFrame(data);
    } else if (event === "windows:action_result") {
      vibrate(15);
      showToast(data.success ? `Window action '${data.action}' successful` : "Action failed", data.success ? "success" : "error");
      setTimeout(fetchAppWindows, 350);
    }
  }

  function setupMainTabs() {
    const navButtons = document.querySelectorAll(".nav-btn");
    navButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        vibrate(10);
        const tab = btn.dataset.tab;
        navButtons.forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");

        document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
        document.getElementById(`tab-${tab}`)?.classList.add("active");
        activeTab = tab;

        if (tab !== "screen" && isScreenStreaming) {
          document.getElementById("btn-toggle-stream")?.click();
        }
        if (tab !== "screen" && isWebcamStreaming) {
          document.getElementById("btn-toggle-webcam")?.click();
        }
        if (tab !== "screen" && isWindowStreaming) {
          window.stopWindowStream?.();
        }

        if (tab === "screen") sendWS("monitors:list");
        if (tab === "files") fetchFileList();
        if (tab === "security") {
          sendWS("sentry:get_status");
          sendWS("security:get_settings");
          sendWS("security:logs");
        }
        if (tab === "system") {
          refreshSystemData();
          if (!statsInterval) statsInterval = setInterval(refreshSystemData, 2000);
        } else {
          if (statsInterval) {
            clearInterval(statsInterval);
            statsInterval = null;
          }
        }
      });
    });
  }

  function setupSubPills() {
    // 1. Remote Sub-Pills (keys, media, presenter, gaming, custom)
    document.querySelectorAll(".sub-pill").forEach((pill) => {
      pill.addEventListener("click", () => {
        vibrate(10);
        document.querySelectorAll(".sub-pill").forEach((p) => p.classList.remove("active"));
        pill.classList.add("active");
        const sub = pill.dataset.sub;
        document.querySelectorAll(".sub-panel").forEach((p) => p.classList.remove("active"));
        document.getElementById(`sub-${sub}`)?.classList.add("active");
      });
    });

    // 2. Live View Sub-Pills (screen, windows, webcam)
    document.querySelectorAll(".view-pill").forEach((pill) => {
      pill.addEventListener("click", () => {
        vibrate(10);
        document.querySelectorAll(".view-pill").forEach((p) => p.classList.remove("active"));
        pill.classList.add("active");
        const view = pill.dataset.view;
        document.querySelectorAll(".view-panel").forEach((p) => p.classList.remove("active"));
        document.getElementById(`view-${view}`)?.classList.add("active");

        if (view === "windows") {
          fetchAppWindows();
        } else if (isWindowStreaming) {
          window.stopWindowStream?.();
        }
      });
    });

    // 3. Files Sub-Pills (files, clipboard)
    document.querySelectorAll(".file-pill").forEach((pill) => {
      pill.addEventListener("click", () => {
        vibrate(10);
        document.querySelectorAll(".file-pill").forEach((p) => p.classList.remove("active"));
        pill.classList.add("active");
        const filetab = pill.dataset.filetab;
        document.querySelectorAll(".file-sub-panel").forEach((p) => p.classList.remove("active"));
        document.getElementById(`filetab-${filetab}`)?.classList.add("active");
        if (filetab === "clipboard") sendWS("clipboard:get");
        if (filetab === "media") loadMediaLibrary(currentActiveMediaFilter, currentSelectedFolder);
      });
    });
  }

  function refreshSystemData() {
    sendWS("system:stats");
    sendWS("devices:list");
  }
  let gestureHudTimeout = null;
  function showGestureHUD(text) {
    const el = document.getElementById("gesture-indicator");
    if (!el) return;
    el.textContent = text;
    el.classList.add("visible");
    if (gestureHudTimeout) clearTimeout(gestureHudTimeout);
    gestureHudTimeout = setTimeout(() => {
      el.classList.remove("visible");
    }, 750);
  }

  function getTouchesCenter(touches) {
    let x = 0, y = 0;
    for (let i = 0; i < touches.length; i++) {
      x += touches[i].clientX;
      y += touches[i].clientY;
    }
    return { x: x / touches.length, y: y / touches.length };
  }

  function setupTrackpad() {
    const surface = document.getElementById("touch-surface");
    const pointer = document.getElementById("virtual-pointer");

    // Speed selector buttons
    document.querySelectorAll(".btn-speed").forEach((btn) => {
      btn.addEventListener("click", () => {
        vibrate(10);
        document.querySelectorAll(".btn-speed").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        sensitivity = parseFloat(btn.dataset.sens || "1.0");
        localStorage.setItem("pulse_sens", sensitivity.toString());
      });
    });

    let touchStartTime = 0;
    let maxFingers = 0;
    let startCenter = { x: 0, y: 0 };
    let lastCenter = { x: 0, y: 0 };
    let initialPinchDist = 0;
    let lastPinchDist = 0;
    let pinchAccum = 0;
    let totalTravelDist = 0;
    let swipeTriggered = false;

    surface.addEventListener("touchstart", (e) => {
      const count = e.touches.length;
      if (count === 1) {
        touchStartTime = Date.now();
        maxFingers = 1;
        totalTravelDist = 0;
        swipeTriggered = false;
        pinchAccum = 0;
        const t = e.touches[0];
        startCenter = { x: t.clientX, y: t.clientY };
        lastCenter = { x: t.clientX, y: t.clientY };

        const rect = surface.getBoundingClientRect();
        pointer.style.left = (t.clientX - rect.left) + "px";
        pointer.style.top = (t.clientY - rect.top) + "px";
        pointer.style.display = "block";
      } else {
        pointer.style.display = "none";
        maxFingers = Math.max(maxFingers, count);
        const center = getTouchesCenter(e.touches);
        startCenter = center;
        lastCenter = center;
        if (count === 2) {
          const d = Math.hypot(e.touches[1].clientX - e.touches[0].clientX, e.touches[1].clientY - e.touches[0].clientY);
          initialPinchDist = d;
          lastPinchDist = d;
          pinchAccum = 0;
        }
      }
    }, { passive: false });

    surface.addEventListener("touchmove", (e) => {
      e.preventDefault();
      const count = e.touches.length;
      maxFingers = Math.max(maxFingers, count);

      if (count === 1 && maxFingers === 1) {
        // --- 1 Finger: Smooth Cursor Movement ---
        const t = e.touches[0];
        const dx = t.clientX - lastCenter.x;
        const dy = t.clientY - lastCenter.y;
        totalTravelDist += Math.hypot(dx, dy);

        if (Math.abs(dx) > 0.4 || Math.abs(dy) > 0.4) {
          sendWS("mouse:move", { dx, dy, sensitivity });
        }
        lastCenter = { x: t.clientX, y: t.clientY };

        const rect = surface.getBoundingClientRect();
        pointer.style.left = Math.max(10, Math.min(rect.width - 10, t.clientX - rect.left)) + "px";
        pointer.style.top = Math.max(10, Math.min(rect.height - 10, t.clientY - rect.top)) + "px";

      } else if (count === 2) {
        // --- 2 Fingers: Pinch-to-Zoom OR Smooth 2D Scroll ---
        const t1 = e.touches[0];
        const t2 = e.touches[1];
        const curDist = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY);
        const curCenter = { x: (t1.clientX + t2.clientX) / 2, y: (t1.clientY + t2.clientY) / 2 };

        const distDiff = curDist - lastPinchDist;
        const centerDx = curCenter.x - lastCenter.x;
        const centerDy = curCenter.y - lastCenter.y;

        totalTravelDist += Math.hypot(centerDx, centerDy) + Math.abs(distDiff);

        // Compare pinch vs scroll displacement from initial contact
        const pinchDeltaFromStart = Math.abs(curDist - initialPinchDist);
        const scrollDeltaFromStart = Math.hypot(curCenter.x - startCenter.x, curCenter.y - startCenter.y);

        if (pinchDeltaFromStart > 14 && pinchDeltaFromStart > scrollDeltaFromStart * 0.6) {
          // Pinch Zoom Action
          pinchAccum += distDiff;
          lastPinchDist = curDist;
          lastCenter = curCenter;

          const ZOOM_THRESHOLD = 14; // pixels of pinch required per zoom step
          if (pinchAccum >= ZOOM_THRESHOLD) {
            sendWS("mouse:zoom", { delta: 1.0 }); // Zoom in
            showGestureHUD("🔍 Zoom In");
            vibrate(10);
            pinchAccum = 0;
          } else if (pinchAccum <= -ZOOM_THRESHOLD) {
            sendWS("mouse:zoom", { delta: -1.0 }); // Zoom out
            showGestureHUD("🔍 Zoom Out");
            vibrate(10);
            pinchAccum = 0;
          }
        } else {
          // 2-Finger Smooth Scroll
          lastPinchDist = curDist;
          const scrollDy = (curCenter.y - lastCenter.y) / 5.0;
          const scrollDx = (curCenter.x - lastCenter.x) / 5.0;
          if (Math.abs(scrollDy) > 0.15 || Math.abs(scrollDx) > 0.15) {
            sendWS("mouse:scroll", { dy: scrollDy, dx: scrollDx });
          }
          lastCenter = curCenter;
        }

      } else if (count === 3 && !swipeTriggered) {
        // --- 3 Fingers: Multitasking Gestures ---
        const center = getTouchesCenter(e.touches);
        const deltaX = center.x - startCenter.x;
        const deltaY = center.y - startCenter.y;
        const travel = Math.hypot(deltaX, deltaY);
        totalTravelDist += travel;

        const SWIPE_THRESHOLD = 32; // Lower threshold (32px) for instant responsiveness
        if (travel > SWIPE_THRESHOLD) {
          swipeTriggered = true;
          if (Math.abs(deltaY) > Math.abs(deltaX)) {
            if (deltaY < -SWIPE_THRESHOLD) {
              // 3 Fingers UP: Task View (Win + Tab)
              sendWS("touchpad:gesture", { gesture: "task_view" });
              showGestureHUD("🪟 Task View (Win+Tab)");
              vibrate([15, 35]);
            } else {
              // 3 Fingers DOWN: Show Desktop (Win + D)
              sendWS("touchpad:gesture", { gesture: "show_desktop" });
              showGestureHUD("🖥️ Show Desktop (Win+D)");
              vibrate([15, 35]);
            }
          } else {
            if (deltaX > SWIPE_THRESHOLD) {
              // 3 Fingers RIGHT: Switch App (Alt + Tab)
              sendWS("touchpad:gesture", { gesture: "alt_tab" });
              showGestureHUD("🔀 Switch App (Alt+Tab)");
              vibrate(20);
            } else {
              // 3 Fingers LEFT: Prev App (Alt + Shift + Tab)
              sendWS("touchpad:gesture", { gesture: "alt_shift_tab" });
              showGestureHUD("🔀 Switch App (Alt+Shift+Tab)");
              vibrate(20);
            }
          }
        }

      } else if (count === 4 && !swipeTriggered) {
        // --- 4 Fingers: Virtual Desktops ---
        const center = getTouchesCenter(e.touches);
        const deltaX = center.x - startCenter.x;
        const SWIPE_THRESHOLD = 32;
        if (Math.abs(deltaX) > SWIPE_THRESHOLD) {
          swipeTriggered = true;
          totalTravelDist += Math.abs(deltaX);
          if (deltaX > SWIPE_THRESHOLD) {
            sendWS("touchpad:gesture", { gesture: "desktop_next" });
            showGestureHUD("🗂️ Desktop ➔ (Ctrl+Win+Right)");
            vibrate([20, 30]);
          } else {
            sendWS("touchpad:gesture", { gesture: "desktop_prev" });
            showGestureHUD("🗂️ ⬅ Desktop (Ctrl+Win+Left)");
            vibrate([20, 30]);
          }
        }
      }
    }, { passive: false });

    surface.addEventListener("touchend", (e) => {
      pointer.style.display = "none";

      if (e.touches.length === 0) {
        const duration = Date.now() - touchStartTime;

        // TAP GESTURE: finger(s) must have lifted within 350ms with minimal travel (<25px)
        if (!swipeTriggered && duration < 350 && totalTravelDist < 25) {
          if (maxFingers === 1) {
            // 1-Finger Tap = Left Click
            vibrate(12);
            sendWS("mouse:click", { button: "left" });
          } else if (maxFingers === 2) {
            // 2-Finger Tap = Right Click (Native Windows Laptop Gesture!)
            vibrate(30);
            sendWS("mouse:click", { button: "right" });
            showGestureHUD("🖱️ Right Click");
          } else if (maxFingers === 3) {
            // 3-Finger Tap = Windows Search (Win + S)
            vibrate(30);
            sendWS("touchpad:gesture", { gesture: "search" });
            showGestureHUD("🔍 Windows Search (Win+S)");
          } else if (maxFingers >= 4) {
            // 4-Finger Tap = Action Center / Notifications (Win + A)
            vibrate(30);
            sendWS("touchpad:gesture", { gesture: "action_center" });
            showGestureHUD("🔔 Notifications (Win+A)");
          }
        }

        // Reset
        maxFingers = 0;
        totalTravelDist = 0;
        swipeTriggered = false;
        pinchAccum = 0;
      }
    });

    document.getElementById("btn-left-click")?.addEventListener("click", () => { vibrate(15); sendWS("mouse:click", { button: "left" }); });
    document.getElementById("btn-middle-click")?.addEventListener("click", () => { vibrate(15); sendWS("mouse:click", { button: "middle" }); });
    document.getElementById("btn-right-click")?.addEventListener("click", () => { vibrate(15); sendWS("mouse:click", { button: "right" }); });
    document.getElementById("btn-scroll-up")?.addEventListener("click", () => { vibrate(10); sendWS("mouse:scroll", { dy: 2 }); });
    document.getElementById("btn-scroll-down")?.addEventListener("click", () => { vibrate(10); sendWS("mouse:scroll", { dy: -2 }); });
  }

  function setupKeysAndShortcuts() {
    const typeForm = document.getElementById("type-form");
    const typeInput = document.getElementById("type-text-input");

    typeForm?.addEventListener("submit", (e) => {
      e.preventDefault();
      const text = typeInput.value;
      if (text) {
        vibrate(15);
        sendWS("keyboard:type", { text });
        typeInput.value = "";
      }
    });

    document.querySelectorAll(".btn-tile, .btn-key-tile").forEach((btn) => {
      btn.addEventListener("click", () => {
        vibrate(15);
        const sc = btn.dataset.shortcut;
        const k = btn.dataset.key;
        if (sc) sendWS("keyboard:shortcut", { shortcut: sc });
        if (k) sendWS("keyboard:key", { key: k });
      });
    });

    document.querySelectorAll(".btn-huge-slide").forEach((btn) => {
      btn.addEventListener("click", () => {
        vibrate(20);
        const sc = btn.dataset.shortcut;
        if (sc) sendWS("keyboard:shortcut", { shortcut: sc });
      });
    });

    document.querySelectorAll(".btn-dpad-key, .btn-action-pad").forEach((btn) => {
      btn.addEventListener("click", () => {
        vibrate(15);
        const k = btn.dataset.key;
        if (k) sendWS("keyboard:key", { key: k });
      });
    });
  }

  function setupScreenViewer() {
    const btnToggle = document.getElementById("btn-toggle-stream");
    const screenVideo = document.getElementById("screen-video");
    const screenImg = document.getElementById("screen-img");
    const placeholder = document.getElementById("screen-placeholder");
    const viewport = document.getElementById("screen-viewport");
    const touchRipple = document.getElementById("touch-ripple");
    const streamBadge = document.getElementById("screen-stream-badge");
    const codecBadge = document.getElementById("screen-stream-codec");

    let peerConnection = null;
    let isWebRTCActive = false;
    let webrtcTimeoutTimer = null;
    let jpegPullTimer = null;

    function setBadge(fpsText, codecText, isRtc) {
      if (streamBadge) streamBadge.textContent = fpsText;
      if (codecBadge) {
        codecBadge.textContent = codecText;
        codecBadge.style.color = isRtc ? "#00F2FE" : "#FBBF24";
        codecBadge.style.borderColor = isRtc ? "rgba(0,242,254,0.3)" : "rgba(251,191,36,0.3)";
      }
    }

    async function startWebRTC() {
      if (!window.RTCPeerConnection) {
        console.warn("[WebRTC] RTCPeerConnection not supported in this browser, falling back to JPEG");
        startJpegStream();
        return;
      }

      try {
        setBadge("🔄 Linking...", "WebRTC", true);
        if (peerConnection) {
          try { peerConnection.close(); } catch (e) {}
          peerConnection = null;
        }

        peerConnection = new RTCPeerConnection({
          iceServers: [],
          bundlePolicy: "max-bundle",
          rtcpMuxPolicy: "require"
        });

        peerConnection.addTransceiver("video", { direction: "recvonly" });

        peerConnection.ontrack = (event) => {
          if (webrtcTimeoutTimer) {
            clearTimeout(webrtcTimeoutTimer);
            webrtcTimeoutTimer = null;
          }
          isWebRTCActive = true;
          screenVideo.srcObject = event.streams[0];
          screenVideo.classList.remove("hidden");
          screenImg.classList.add("hidden");
          placeholder.classList.add("hidden");
          btnToggle.textContent = "⏹ Stop";
          btnToggle.style.background = "#f43f5e";
          setBadge("⚡ 60 FPS", "H.264 WebRTC", true);
          showToast("⚡ 60 FPS WebRTC Stream Connected!", "success");
        };

        peerConnection.oniceconnectionstatechange = () => {
          if (peerConnection && (peerConnection.iceConnectionState === "failed" || peerConnection.iceConnectionState === "disconnected")) {
            console.warn("[WebRTC] Connection failed, switching to Turbo JPEG mode");
            fallbackToJpeg();
          }
        };

        const offer = await peerConnection.createOffer();
        await peerConnection.setLocalDescription(offer);

        // Allow ICE candidate gathering to populate local host candidates
        if (peerConnection.iceGatheringState !== "complete") {
          await new Promise((resolve) => {
            function checkIce() {
              if (peerConnection && peerConnection.iceGatheringState === "complete") {
                peerConnection.removeEventListener("icegatheringstatechange", checkIce);
                resolve();
              }
            }
            peerConnection.addEventListener("icegatheringstatechange", checkIce);
            setTimeout(resolve, 800);
          });
        }

        sendWS("webrtc:offer", {
          sdp: peerConnection.localDescription.sdp,
          type: peerConnection.localDescription.type,
          fps: 60,
          maxWidth: 1280
        });

        // 4 second timeout fallback to JPEG if WebRTC takes too long
        webrtcTimeoutTimer = setTimeout(() => {
          if (!isWebRTCActive && isScreenStreaming) {
            console.warn("[WebRTC] Handshake timed out, switching to Turbo JPEG mode");
            fallbackToJpeg();
          }
        }, 4000);

      } catch (err) {
        console.error("[WebRTC Setup Error]:", err);
        fallbackToJpeg();
      }
    }

    window.handleWebRTCAnswer = async (data) => {
      if (peerConnection && data && data.sdp) {
        try {
          await peerConnection.setRemoteDescription(new RTCSessionDescription({
            sdp: data.sdp,
            type: data.type || "answer"
          }));
        } catch (err) {
          console.error("[WebRTC setRemoteDescription Error]:", err);
          fallbackToJpeg();
        }
      }
    };

    window.handleWebRTCError = (data) => {
      console.warn("[WebRTC Error from server]:", data);
      fallbackToJpeg();
    };

    function fallbackToJpeg() {
      if (peerConnection) {
        try { peerConnection.close(); } catch (e) {}
        peerConnection = null;
      }
      isWebRTCActive = false;
      if (isScreenStreaming) {
        startJpegStream();
      }
    }

    function startJpegStream() {
      isWebRTCActive = false;
      screenVideo.classList.add("hidden");
      screenImg.classList.remove("hidden");
      placeholder.classList.add("hidden");
      btnToggle.textContent = "⏹ Stop";
      btnToggle.style.background = "#f43f5e";
      setBadge("⚡ 30 FPS", "Turbo JPEG", false);
      pullScreenFrame();
    }

    function pullScreenFrame() {
      if (isScreenStreaming && !isWebRTCActive && activeTab === "screen") {
        sendWS("screen:frame", { quality: 55, maxWidth: 1080, monitor_id: selectedMonitorId });
      }
    }

    window.renderScreenFrame = (frameB64) => {
      if (isWebRTCActive) return;
      screenImg.src = frameB64;
      if (isScreenStreaming && !isWebRTCActive && activeTab === "screen") {
        if (jpegPullTimer) clearTimeout(jpegPullTimer);
        // Turbo 15ms frame pacing (~30-35 FPS responsive)
        jpegPullTimer = setTimeout(pullScreenFrame, 15);
      }
    };

    function stopScreenStream() {
      if (webrtcTimeoutTimer) {
        clearTimeout(webrtcTimeoutTimer);
        webrtcTimeoutTimer = null;
      }
      if (jpegPullTimer) {
        clearTimeout(jpegPullTimer);
        jpegPullTimer = null;
      }
      if (peerConnection) {
        try { peerConnection.close(); } catch (e) {}
        peerConnection = null;
      }
      isWebRTCActive = false;
      sendWS("webrtc:stop");

      if (screenVideo.srcObject) {
        try {
          screenVideo.srcObject.getTracks().forEach((t) => t.stop());
        } catch (e) {}
        screenVideo.srcObject = null;
      }
      screenVideo.classList.add("hidden");
      screenImg.classList.add("hidden");
      placeholder.classList.remove("hidden");
      btnToggle.textContent = "▶ Start Stream";
      btnToggle.style.background = "";
      setBadge("⚡ 60 FPS", "WebRTC", true);
    }

    btnToggle?.addEventListener("click", () => {
      vibrate(15);
      isScreenStreaming = !isScreenStreaming;
      if (isScreenStreaming) {
        startWebRTC();
      } else {
        stopScreenStream();
      }
    });

    // Touch-to-click mapping on live screen (Works on both WebRTC Video and JPEG Img!)
    function handleScreenClick(e) {
      const activeEl = (!screenVideo.classList.contains("hidden")) ? screenVideo : screenImg;
      const rect = activeEl.getBoundingClientRect();
      if (!rect || rect.width === 0 || rect.height === 0) return;

      const clickX = e.clientX - rect.left;
      const clickY = e.clientY - rect.top;
      const relX = clickX / rect.width;
      const relY = clickY / rect.height;

      // Show visual touch ripple
      if (touchRipple) {
        touchRipple.style.left = `${clickX}px`;
        touchRipple.style.top = `${clickY}px`;
        touchRipple.classList.remove("active");
        void touchRipple.offsetWidth;
        touchRipple.classList.add("active");
      }

      if (relX >= 0 && relX <= 1 && relY >= 0 && relY <= 1) {
        vibrate(20);
        sendWS("mouse:click_rel", {
          rel_x: relX,
          rel_y: relY,
          monitor_id: selectedMonitorId,
          button: "left"
        });
      }
    }

    screenVideo.addEventListener("click", handleScreenClick);
    screenImg.addEventListener("click", handleScreenClick);

    document.getElementById("btn-screen-fs")?.addEventListener("click", () => {
      vibrate(15);
      if (!document.fullscreenElement) {
        viewport.requestFullscreen().catch(() => {});
      } else {
        document.exitFullscreen().catch(() => {});
      }
    });
  }

  function renderMonitors(monitors) {
    monitorsList = monitors;
    const container = document.getElementById("monitors-pill-container");
    if (!container) return;
    container.innerHTML = monitors.map((m) => `
      <button class="btn-mon-pill ${m.id === selectedMonitorId ? 'active' : ''}" onclick="window.selectMonitor(${m.id})">
        ${m.name} (${m.width}×${m.height})
      </button>
    `).join("");
  }

  window.selectMonitor = (monId) => {
    vibrate(15);
    selectedMonitorId = monId;
    sendWS("monitors:select", { monitor_id: monId });
    renderMonitors(monitorsList);
  };

  function setupWebcam() {
    const btnToggle = document.getElementById("btn-toggle-webcam");
    const webcamImg = document.getElementById("webcam-img");
    const placeholder = document.getElementById("webcam-placeholder");

    btnToggle?.addEventListener("click", () => {
      vibrate(15);
      isWebcamStreaming = !isWebcamStreaming;
      if (isWebcamStreaming) {
        btnToggle.textContent = "⏹ Stop";
        btnToggle.style.background = "#f43f5e";
        webcamImg.classList.remove("hidden");
        placeholder.classList.add("hidden");
        pullWebcamFrame();
      } else {
        btnToggle.textContent = "▶ Start Camera";
        btnToggle.style.background = "";
        webcamImg.classList.add("hidden");
        placeholder.classList.remove("hidden");
        sendWS("webcam:stop");
      }
    });

    function pullWebcamFrame() {
      if (isWebcamStreaming && activeTab === "screen") {
        sendWS("webcam:frame", { camera_id: 0, quality: 60 });
      }
    }

    window.renderWebcamFrame = (frameB64) => {
      webcamImg.src = frameB64;
      if (isWebcamStreaming && activeTab === "screen") {
        setTimeout(pullWebcamFrame, 70);
      }
    };
  }

  // --- 🪟 Taskbar Running Apps Live Monitor & Remote Controls ---
  function fetchAppWindows() {
    const grid = document.getElementById("app-windows-grid");
    if (grid && (!cachedAppWindows || cachedAppWindows.length === 0)) {
      grid.innerHTML = `<div class="loading-text"><span class="pulse-alarm-dot" style="display:inline-block; margin-right:6px;"></span> Scanning taskbar apps & capturing previews...</div>`;
    }
    sendWS("windows:thumbnails");
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function renderAppWindows(windows) {
    cachedAppWindows = windows || [];
    const grid = document.getElementById("app-windows-grid");
    if (!grid) return;

    if (!windows || windows.length === 0) {
      grid.innerHTML = `
        <div class="empty-state" style="padding: 24px 12px; text-align: center; color: var(--text-muted); grid-column: 1 / -1;">
          <div style="font-size: 32px; margin-bottom: 8px;">🪟</div>
          <p style="font-weight: 700; color: #fff;">No active taskbar apps found</p>
          <p style="font-size: 12px; margin-top: 4px;">Open an application (Chrome, VS Code, Explorer) on your PC and tap Refresh.</p>
        </div>`;
      return;
    }

    grid.innerHTML = windows.map((win) => {
      const safeTitle = escapeHtml(win.title || "Window");
      const safeProc = escapeHtml(win.process_name || win.process || "");
      const icon = win.icon || "🪟";
      const thumbSrc = win.thumbnail || "";
      const isMinimized = !!win.is_minimized;

      return `
        <div class="app-window-card" id="app-card-${win.hwnd}">
          <div class="app-window-card-header">
            <div class="app-window-info">
              <span class="app-window-icon">${icon}</span>
              <div style="min-width: 0;">
                <div class="app-window-title" title="${safeTitle}">${safeTitle}</div>
                <div class="app-window-proc">
                  ${safeProc}
                  ${isMinimized ? '<span style="color: var(--cyan); font-weight:700; margin-left:4px;">(💤 Minimized)</span>' : '<span style="color: var(--green); margin-left:4px;">(Active)</span>'}
                </div>
              </div>
            </div>
            <button class="btn-win-act btn-win-act-primary" style="flex: initial; padding: 4px 8px; font-size: 10px;" onclick="window.startWindowStream(${win.hwnd})">
              ▶ Stream
            </button>
          </div>

          <div class="app-window-thumb-wrap" onclick="window.startWindowStream(${win.hwnd})" title="Tap to Stream Live">
            ${thumbSrc ? `<img src="${thumbSrc}" class="app-window-thumb-img" alt="${safeTitle}">` : `<div style="font-size: 36px; opacity: 0.35;">${icon}</div>`}
            <div class="app-window-overlay-play">▶</div>
          </div>

          <div class="app-window-card-actions">
            <button class="btn-win-act" onclick="window.actionWindow(${win.hwnd}, 'focus')" title="Bring window to front">
              ⚡ Focus
            </button>
            <button class="btn-win-act" onclick="window.actionWindow(${win.hwnd}, 'minimize')" title="Minimize">
              🗕 Min
            </button>
            <button class="btn-win-act" onclick="window.actionWindow(${win.hwnd}, 'maximize')" title="Maximize">
              🗖 Max
            </button>
            <button class="btn-win-act btn-win-act-danger" onclick="window.actionWindow(${win.hwnd}, 'close')" title="Close Window">
              ❌ Close
            </button>
          </div>
        </div>
      `;
    }).join("");
  }

  window.startWindowStream = function (hwnd) {
    vibrate(15);
    const win = cachedAppWindows.find((w) => w.hwnd == hwnd) || {};
    const title = win.title || "App Window";
    const icon = win.icon || "🪟";
    const proc = win.process_name || win.process || "";

    // If window is minimized, bring it to front so PrintWindow has live desktop pixels
    if (win.is_minimized) {
      window.actionWindow(hwnd, "focus");
      win.is_minimized = false;
    }

    isWindowStreaming = true;
    activeWindowHwnd = hwnd;

    const streamContainer = document.getElementById("app-stream-container");
    const activeIcon = document.getElementById("active-app-icon");
    const activeTitle = document.getElementById("active-app-title");
    const activeSub = document.getElementById("active-app-sub");

    if (streamContainer) {
      streamContainer.classList.remove("hidden");
      streamContainer.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    if (activeIcon) activeIcon.textContent = icon;
    if (activeTitle) activeTitle.textContent = title;
    if (activeSub) activeSub.textContent = proc;

    showToast(`Streaming: ${title}`, "info");
    pullWindowStreamFrame();
  };

  window.stopWindowStream = function () {
    vibrate(10);
    isWindowStreaming = false;
    activeWindowHwnd = null;

    const streamContainer = document.getElementById("app-stream-container");
    const streamImg = document.getElementById("app-stream-img");
    if (streamContainer) streamContainer.classList.add("hidden");
    if (streamImg) streamImg.src = "";
  };

  window.actionWindow = function (hwnd, action) {
    vibrate(15);
    if (action === "close") {
      const win = cachedAppWindows.find((w) => w.hwnd == hwnd);
      const title = win?.title ? `"${win.title}"` : "this window";
      if (!confirm(`Are you sure you want to close ${title}?`)) {
        return;
      }
    }
    sendWS("windows:action", { hwnd: hwnd, action: action });
  };

  function pullWindowStreamFrame() {
    if (isWindowStreaming && activeWindowHwnd && activeTab === "screen") {
      sendWS("windows:frame", { hwnd: activeWindowHwnd, quality: 65, maxWidth: 960 });
    }
  }

  function renderWindowStreamFrame(data) {
    if (!isWindowStreaming || !activeWindowHwnd || data.hwnd != activeWindowHwnd) return;
    const img = document.getElementById("app-stream-img");
    if (img && data.frame) {
      img.src = data.frame;
    }
    if (isWindowStreaming && activeTab === "screen") {
      setTimeout(pullWindowStreamFrame, 80);
    }
  }

  function setupAppWindowsMonitor() {
    const btnRefresh = document.getElementById("btn-refresh-windows");
    btnRefresh?.addEventListener("click", () => {
      vibrate(10);
      fetchAppWindows();
    });

    const btnStopStream = document.getElementById("btn-stop-app-stream");
    btnStopStream?.addEventListener("click", () => {
      window.stopWindowStream();
    });

    const btnFocusActive = document.getElementById("btn-focus-active-app");
    btnFocusActive?.addEventListener("click", () => {
      if (activeWindowHwnd) {
        window.actionWindow(activeWindowHwnd, "focus");
      }
    });
  }

  function setupMediaControls() {
    document.querySelectorAll(".btn-media-round, .btn-media-round-primary, .btn-volume-box").forEach((btn) => {
      btn.addEventListener("click", () => {
        vibrate(20);
        const sc = btn.dataset.shortcut;
        if (sc) sendWS("media:command", { command: sc });
      });
    });
  }
  function setupFileManager() {
    const uploader = document.getElementById("file-uploader");
    const hud = document.getElementById("transfer-hud");
    const hudFile = document.getElementById("transfer-filename");
    const hudPct = document.getElementById("transfer-percent");
    const barFill = document.getElementById("transfer-bar-fill");
    const hudSpeed = document.getElementById("transfer-speed");
    const hudEta = document.getElementById("transfer-eta");

    uploader?.addEventListener("change", (e) => {
      const file = e.target.files[0];
      if (!file) return;
      hud.classList.remove("hidden");
      hudFile.textContent = `Uploading: ${file.name}`;
      
      const formData = new FormData();
      formData.append("file", file);
      const xhr = new XMLHttpRequest();
      const startTime = Date.now();

      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          const percent = Math.round((event.loaded / event.total) * 100);
          hudPct.textContent = `${percent}%`;
          barFill.style.width = `${percent}%`;
          const elapsedSec = (Date.now() - startTime) / 1000 || 0.1;
          const speedMBs = (event.loaded / (1024 * 1024)) / elapsedSec;
          hudSpeed.textContent = `Speed: ${speedMBs.toFixed(1)} MB/s`;
          const remainingBytes = event.total - event.loaded;
          const etaSec = Math.round(remainingBytes / (speedMBs * 1024 * 1024 || 1));
          hudEta.textContent = `ETA: ${etaSec}s`;
        }
      };

      xhr.onload = () => {
        hud.classList.add("hidden");
        vibrate(30);
        if (xhr.status === 200) {
          alert(`✅ "${file.name}" uploaded to PC!`);
          fetchFileList(currentBrowsePath);
        } else {
          alert("Upload failed.");
        }
      };

      xhr.open("POST", `/api/files/upload?dir=${encodeURIComponent(currentBrowsePath || "")}`);
      xhr.setRequestHeader("X-Session-Token", sessionToken);
      xhr.send(formData);
    });
  }

  function fetchFileList(path = "") {
    sendWS("files:list", { path });
  }

  function renderFileList(data) {
    const container = document.getElementById("file-list-container");
    const breadcrumb = document.getElementById("crumb-current-path");
    const quickFolders = document.getElementById("quick-folders");

    currentBrowsePath = data.current_path || "";
    breadcrumb.textContent = currentBrowsePath;

    if (data.quick_folders && quickFolders) {
      quickFolders.innerHTML = data.quick_folders.map(f => `
        <button class="btn-folder-tag" onclick="window.browsePath('${f.path.replace(/\\/g, "/")}')">
          📁 ${f.name}
        </button>
      `).join("");
    }

    if (!data.items || data.items.length === 0) {
      container.innerHTML = `<div class="loading-text">Empty Folder</div>`;
      return;
    }

    let html = "";
    if (data.parent_path) {
      html += `
        <div class="file-item" onclick="window.browsePath('${data.parent_path.replace(/\\/g, "/")}')">
          <div class="file-info">
            <span style="font-size: 20px;">📁</span>
            <span class="file-name" style="font-weight: 800;">.. (Parent Folder)</span>
          </div>
        </div>
      `;
    }

    data.items.forEach((item) => {
      const isDir = item.is_dir;
      const icon = isDir ? "📁" : (item.ext === "pdf" ? "📄" : (["jpg","png","webp"].includes(item.ext) ? "🖼️" : "📦"));
      const sizeStr = isDir ? "" : formatBytes(item.size);
      const cleanPath = item.path.replace(/\\/g, "/");

      if (isDir) {
        html += `
          <div class="file-item" onclick="window.browsePath('${cleanPath}')">
            <div class="file-info">
              <span style="font-size: 20px;">${icon}</span>
              <span class="file-name">${item.name}</span>
            </div>
            <span style="font-size: 11px; color: var(--muted); font-weight: 700;">Folder</span>
          </div>
        `;
      } else {
        html += `
          <div class="file-item">
            <div class="file-info">
              <span style="font-size: 20px;">${icon}</span>
              <span class="file-name">${item.name}</span>
            </div>
            <div class="flex gap-2" style="align-items: center;">
              <span style="font-size: 11px; color: var(--text-muted); font-weight: 700;">${sizeStr}</span>
              <a href="/api/files/download?path=${encodeURIComponent(item.path)}&token=${sessionToken}" download class="btn btn-sm btn-primary" style="padding: 6px 12px; font-size: 11px;">⬇ Save</a>
            </div>
          </div>
        `;
      }
    });

    container.innerHTML = html;
  }

  window.browsePath = (path) => {
    vibrate(10);
    fetchFileList(path);
  };

  function formatBytes(bytes) {
    if (!bytes) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  }

  function setupClipboard() {
    document.getElementById("btn-get-clipboard")?.addEventListener("click", () => {
      vibrate(15);
      sendWS("clipboard:get");
    });

    document.getElementById("btn-set-clipboard")?.addEventListener("click", () => {
      const text = document.getElementById("clip-phone-text").value;
      if (text) {
        vibrate(15);
        sendWS("clipboard:set", { text });
      }
    });

    document.getElementById("btn-clear-clipboard")?.addEventListener("click", () => {
      vibrate(20);
      if (confirm("Clear PC Clipboard?")) {
        sendWS("clipboard:clear");
      }
    });
  }

  function renderClipboardHistory(history) {
    const container = document.getElementById("clip-history-container");
    if (!container) return;
    if (!history || history.length === 0) {
      container.innerHTML = `<span style="font-size: 12px; color: var(--muted);">No clipboard history</span>`;
      return;
    }
    container.innerHTML = history.map((item) => `
      <div class="clip-chip" onclick="window.useClipHistory('${encodeURIComponent(item)}')">
        ${item.replace(/</g, "&lt;")}
      </div>
    `).join("");
  }

  window.useClipHistory = (encodedItem) => {
    vibrate(15);
    const item = decodeURIComponent(encodedItem);
    document.getElementById("clip-phone-text").value = item;
  };

  function setupDashboard() {
    // Find My PC
    document.getElementById("btn-find-pc-toggle")?.addEventListener("click", () => {
      vibrate(20);
      if (!isFindPcRinging) sendWS("find_pc:start");
      else sendWS("find_pc:stop");
    });

    document.getElementById("btn-revoke-all")?.addEventListener("click", () => {
      vibrate(30);
      if (confirm("Disconnect and revoke all devices?")) {
        sendWS("devices:revoke_all");
      }
    });
  }

  function updateFindPcStatus(success, message) {
    const btn = document.getElementById("btn-find-pc-toggle");
    if (!btn) return;
    if (message.includes("playing") || message.includes("already")) {
      isFindPcRinging = true;
      btn.textContent = "🛑 Stop Sound";
      btn.classList.remove("btn-primary");
      btn.classList.add("btn-danger");
      vibrate(40);
    } else {
      isFindPcRinging = false;
      btn.textContent = "Ring PC";
      btn.classList.remove("btn-danger");
      btn.classList.add("btn-primary");
      vibrate(20);
    }
  }

  function renderQuickActions(apps) {
    const grid = document.getElementById("quick-actions-grid");
    if (!grid) return;
    const badgeColors = {
      chrome: "badge-blue",
      vscode: "badge-cyan",
      explorer: "badge-amber",
      notepad: "badge-green",
      downloads: "badge-purple",
      taskmgr: "badge-orange",
      terminal: "badge-dark",
      calc: "badge-indigo",
      settings: "badge-blue"
    };
    grid.innerHTML = apps.map((app) => {
      const badgeClass = badgeColors[app.key] || "badge-blue";
      return `
        <button class="btn-tile" onclick="window.launchApp('${app.key}')">
          <span class="tile-icon-badge ${badgeClass}">${app.icon}</span>
          <span class="tile-text">${app.name}</span>
        </button>
      `;
    }).join("");
  }

  window.launchApp = (appKey) => {
    vibrate(20);
    sendWS("app:launch", { app_key: appKey });
  };

  let lastBatteryAlert = null;

  function renderSystemStats(data) {
    if (!data) return;

    // 1. CPU
    const cpuEl = document.getElementById("stat-cpu");
    const barCpu = document.getElementById("bar-cpu");
    if (cpuEl) cpuEl.textContent = `${data.cpu_percent}%`;
    if (barCpu) barCpu.style.width = `${data.cpu_percent}%`;

    // 2. RAM
    const ramEl = document.getElementById("stat-ram");
    const barRam = document.getElementById("bar-ram");
    if (ramEl && data.memory) ramEl.textContent = `${data.memory.used_gb} / ${data.memory.total_gb} GB`;
    if (barRam && data.memory) barRam.style.width = `${data.memory.percent}%`;

    // 3. Disk
    const diskEl = document.getElementById("stat-disk");
    const barDisk = document.getElementById("bar-disk");
    if (diskEl && data.disk) {
      diskEl.textContent = `${data.disk.used_gb} / ${data.disk.total_gb} GB`;
      if (barDisk) barDisk.style.width = `${data.disk.percent}%`;
    }

    // 4. Network & CPU Model
    const netEl = document.getElementById("stat-net");
    if (netEl && data.network) {
      netEl.textContent = `▲ ${data.network.upload_kbps} KB/s | ▼ ${data.network.download_kbps} KB/s`;
    }
    const cpuModelEl = document.getElementById("stat-cpu-model");
    if (cpuModelEl) cpuModelEl.textContent = data.cpu_model || "Multi-Core Processor";

    // 5. Battery HUD & Smart Alerts
    const batPercentEl = document.getElementById("stat-battery-percent");
    const barBattery = document.getElementById("bar-battery");
    const batStatusEl = document.getElementById("stat-battery-status");
    const batTimeEl = document.getElementById("stat-battery-time");
    const batIcon = document.getElementById("battery-icon");

    if (data.battery) {
      const pct = data.battery.percent;
      const plugged = data.battery.power_plugged;

      if (batPercentEl) batPercentEl.textContent = `${pct}%`;
      if (barBattery) {
        barBattery.style.width = `${pct}%`;
        if (pct <= 20) barBattery.style.background = "#EF4444";
        else if (pct <= 40) barBattery.style.background = "#F59E0B";
        else barBattery.style.background = "linear-gradient(90deg, #10B981, #06B6D4)";
      }

      if (batIcon) batIcon.textContent = plugged ? "⚡" : (pct <= 20 ? "🪫" : "🔋");
      if (batStatusEl) batStatusEl.textContent = plugged ? "⚡ Charging (AC Adapter Connected)" : "🔋 On Battery Power";

      if (batTimeEl) {
        if (data.battery.secsleft && data.battery.secsleft > 0) {
          const hrs = Math.floor(data.battery.secsleft / 3600);
          const mins = Math.floor((data.battery.secsleft % 3600) / 60);
          batTimeEl.textContent = `~${hrs}h ${mins}m remaining`;
        } else {
          batTimeEl.textContent = plugged ? "AC Connected" : "Calculating...";
        }
      }

      // Smart Battery Alerts
      if (pct >= 99 && plugged && lastBatteryAlert !== "full") {
        lastBatteryAlert = "full";
        vibrate([100, 50, 100, 50, 200]);
        showToast("⚡ Laptop Fully Charged (100%)! Unplug charger to preserve battery health.", "info");
      } else if (pct <= 20 && !plugged && lastBatteryAlert !== "low") {
        lastBatteryAlert = "low";
        vibrate([200, 100, 200]);
        showToast("⚠️ Battery Low (20%)! Connect PC charger now.", "error");
      } else if (pct > 25 && pct < 95) {
        lastBatteryAlert = null;
      }
    } else {
      if (batPercentEl) batPercentEl.textContent = "AC";
      if (barBattery) barBattery.style.width = "100%";
      if (batStatusEl) batStatusEl.textContent = "🔌 Desktop AC Power";
      if (batTimeEl) batTimeEl.textContent = "Unlimited";
    }

    // 6. Sync Toggles
    const toggleWalk = document.getElementById("toggle-walkaway-lock");
    if (toggleWalk && typeof data.walkaway_lock_enabled === "boolean") {
      toggleWalk.checked = data.walkaway_lock_enabled;
    }

    const toggleGuard = document.getElementById("toggle-cctv-guard");
    if (toggleGuard && typeof data.guard_mode_active === "boolean") {
      toggleGuard.checked = data.guard_mode_active;
    }

    // 7. Brightness sync
    if (typeof data.brightness === "number") {
      updateBrightnessUI(data.brightness);
    }

    // 8. Last intruder snapshot
    if (data.last_intruder && data.last_intruder.photo) {
      updateIntruderPreview(data.last_intruder);
    }
  }

  function renderPairedDevices(devices) {
    const container = document.getElementById("paired-devices-container");
    if (!container) return;
    if (!devices || devices.length === 0) {
      container.innerHTML = `<span style="font-size: 12px; color: var(--text-muted);">No paired devices</span>`;
      return;
    }
    container.innerHTML = devices.map(d => `
      <div class="device-card">
        <div class="flex gap-2" style="align-items: center;">
          <span class="status-dot ${d.is_online ? 'online' : ''}"></span>
          <strong style="font-size: 14px;">${d.name}</strong>
          <span style="font-size: 11px; color: var(--text-muted);">(${d.last_seen_str})</span>
        </div>
        <button class="btn btn-sm btn-danger" onclick="window.revokeDevice('${d.device_id}')">Revoke</button>
      </div>
    `).join("");
  }

  window.revokeDevice = (deviceId) => {
    vibrate(20);
    if (confirm("Revoke this device?")) {
      sendWS("devices:revoke", { device_id: deviceId });
    }
  };

  function setupCustomButtons() {
    renderCustomButtons();
    const modal = document.getElementById("modal-add-button");
    document.getElementById("btn-add-custom-btn")?.addEventListener("click", () => { modal.classList.remove("hidden"); });
    document.getElementById("btn-cancel-cust-btn")?.addEventListener("click", () => { modal.classList.add("hidden"); });

    document.getElementById("btn-save-cust-btn")?.addEventListener("click", () => {
      const name = document.getElementById("cust-btn-name").value.trim();
      const icon = document.getElementById("cust-btn-icon").value;
      const type = document.getElementById("cust-btn-action-type").value;
      const target = document.getElementById("cust-btn-target").value.trim();

      if (name && target) {
        vibrate(15);
        customButtons.push({ id: Date.now().toString(), name, icon, type, target });
        localStorage.setItem("pulse_custom_buttons", JSON.stringify(customButtons));
        modal.classList.add("hidden");
        document.getElementById("cust-btn-name").value = "";
        document.getElementById("cust-btn-target").value = "";
        renderCustomButtons();
      }
    });

    window.triggerCustomButton = (btnId) => {
      const btn = customButtons.find(b => b.id === btnId);
      if (btn) {
        vibrate(20);
        if (btn.type === "app") {
          sendWS("app:launch", { app_key: btn.target });
        } else if (btn.type === "action") {
          sendWS("system:action", { action: btn.target });
        } else {
          sendWS("keyboard:shortcut", { shortcut: btn.target });
        }
      }
    };
  }

  function renderCustomButtons() {
    const container = document.getElementById("custom-buttons-container");
    if (!container) return;
    container.innerHTML = customButtons.map((btn) => `
      <button class="btn-tile" onclick="window.triggerCustomButton('${btn.id}')">
        <span class="tile-icon-badge badge-blue">${btn.icon}</span>
        <span class="tile-text">${btn.name}</span>
      </button>
    `).join("");
  }

  function setupEmergencyLock() {
    document.getElementById("btn-emergency-lock")?.addEventListener("click", (e) => {
      e.preventDefault();
      vibrate(40);
      sendWS("system:action", { action: "lock" });
      showToast("🔒 Locking PC...", "info");
    });
  }

  // --- 1. Boss / Panic Key (Anti-Spy) ---
  function setupBossKey() {
    const triggerPanic = (e) => {
      e?.preventDefault();
      vibrate([50, 50, 100]);
      sendWS("system:panic");
      showToast("🚨 Boss Key Triggered: Clearing screen & muting audio!", "error");
    };

    document.getElementById("btn-panic-mode")?.addEventListener("click", triggerPanic);
    document.getElementById("btn-panic-banner")?.addEventListener("click", triggerPanic);
  }

  // --- 2. Screen Brightness Control ---
  let brightnessDebounce = null;
  function setupBrightnessControl() {
    const slider = document.getElementById("brightness-slider");
    const badge = document.getElementById("brightness-val-badge");

    slider?.addEventListener("input", () => {
      const val = parseInt(slider.value, 10);
      if (badge) badge.textContent = `${val}%`;
      clearTimeout(brightnessDebounce);
      brightnessDebounce = setTimeout(() => {
        sendWS("brightness:set", { level: val });
      }, 100);
    });

    document.querySelectorAll(".btn-preset-chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        vibrate(15);
        const val = parseInt(btn.dataset.brightness, 10);
        if (slider) slider.value = val;
        if (badge) badge.textContent = `${val}%`;
        sendWS("brightness:set", { level: val });
      });
    });
  }

  function updateBrightnessUI(level) {
    const slider = document.getElementById("brightness-slider");
    const badge = document.getElementById("brightness-val-badge");
    if (slider && document.activeElement !== slider) slider.value = level;
    if (badge) badge.textContent = `${level}%`;
  }

  // --- 3. Smart Security & Anti-Theft Sentry Engine ---
  let sentryCountdownInterval = null;
  let isSentryArmed = false;
  let isSentryRinging = false;
  let phoneAudioContext = null;
  let phoneOscillator = null;
  let phoneSirenTimer = null;
  let isPhoneSirenActive = false;

  function startPhoneSirenTone() {
    if (isPhoneSirenActive) return;
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      if (!phoneAudioContext || phoneAudioContext.state === "closed") {
        phoneAudioContext = new AudioCtx();
      }
      if (phoneAudioContext.state === "suspended") {
        phoneAudioContext.resume().catch(() => {});
      }
      const osc = phoneAudioContext.createOscillator();
      const gain = phoneAudioContext.createGain();

      osc.type = "sawtooth";
      osc.frequency.setValueAtTime(800, phoneAudioContext.currentTime);
      gain.gain.setValueAtTime(0.35, phoneAudioContext.currentTime);

      let up = true;
      let f = 800;
      if (phoneSirenTimer) clearInterval(phoneSirenTimer);
      phoneSirenTimer = setInterval(() => {
        if (!isPhoneSirenActive || !phoneAudioContext || phoneAudioContext.state === "closed") {
          clearInterval(phoneSirenTimer);
          phoneSirenTimer = null;
          return;
        }
        f = up ? f + 70 : f - 70;
        if (f >= 1600) up = false;
        if (f <= 750) up = true;
        try {
          osc.frequency.setValueAtTime(f, phoneAudioContext.currentTime);
        } catch (e) {}
      }, 40);

      osc.connect(gain);
      gain.connect(phoneAudioContext.destination);
      osc.start();
      phoneOscillator = osc;
      isPhoneSirenActive = true;
    } catch (e) {
      console.log("Audio siren err:", e);
    }
  }

  function stopPhoneSirenTone() {
    isPhoneSirenActive = false;
    if (phoneSirenTimer) {
      clearInterval(phoneSirenTimer);
      phoneSirenTimer = null;
    }
    if (phoneOscillator) {
      try { phoneOscillator.stop(); phoneOscillator.disconnect(); } catch (e) {}
      phoneOscillator = null;
    }
    if (phoneAudioContext) {
      try { phoneAudioContext.close(); } catch (e) {}
      phoneAudioContext = null;
    }
  }

  function setupSecurityControls() {
    // 1. Hero Anti-Theft Sentry Arm/Disarm Toggle
    const btnSentry = document.getElementById("btn-toggle-sentry");
    btnSentry?.addEventListener("click", () => {
      vibrate(30);
      if (isSentryArmed || isSentryRinging || sentryCountdownInterval !== null) {
        // Disarm or Cancel Countdown
        if (sentryCountdownInterval !== null) {
          clearInterval(sentryCountdownInterval);
          sentryCountdownInterval = null;
        }
        sendWS("sentry:disarm");
        updateSentryUI({ active: false, ringing: false });
        showToast("🟢 Disarming Sentry...", "info");
      } else {
        // Arm with 10s countdown
        sendWS("sentry:arm", { grace_seconds: 10 });
        startSentryArmingCountdown(10);
      }
    });

    // 2. Disarm button inside modal
    document.getElementById("btn-modal-disarm-sentry")?.addEventListener("click", () => {
      vibrate(40);
      sendWS("sentry:disarm");
      stopPhoneSirenTone();
      document.getElementById("modal-intruder-alert")?.classList.add("hidden");
      showToast("🟢 Sentry Disarmed & Siren Stopped!", "success");
    });

    // 3. Emergency Actions in Security Tab
    document.getElementById("btn-sec-panic")?.addEventListener("click", () => {
      vibrate([50, 50, 100]);
      sendWS("system:panic");
      showToast("🚨 Boss Key: Desktop shown & audio muted!", "error");
    });

    document.getElementById("btn-sec-lock")?.addEventListener("click", () => {
      vibrate(30);
      sendWS("system:action", { action: "lock" });
      showToast("🔒 Workstation Locked", "info");
    });

    document.getElementById("btn-sec-find-pc")?.addEventListener("click", () => {
      vibrate(25);
      if (isFindPcRinging) {
        sendWS("find_pc:stop");
      } else {
        sendWS("find_pc:start");
      }
    });

    document.getElementById("btn-sec-sleep")?.addEventListener("click", () => {
      if (confirm("Put PC into Sleep mode?")) {
        vibrate(30);
        sendWS("system:action", { action: "sleep" });
      }
    });

    // 4. Refresh Audit Logs
    document.getElementById("btn-refresh-sec-logs")?.addEventListener("click", () => {
      vibrate(15);
      sendWS("security:logs");
    });

    // 5. Walk-Away Auto-Lock
    const toggleWalk = document.getElementById("toggle-walkaway-lock");
    toggleWalk?.addEventListener("change", () => {
      vibrate(20);
      sendWS("settings:walkaway_lock", { enabled: toggleWalk.checked });
      showToast(`Walk-Away Auto-Lock ${toggleWalk.checked ? "Enabled" : "Disabled"}`, "info");
    });

    // 6. CCTV Intruder Guard
    const toggleGuard = document.getElementById("toggle-cctv-guard");
    toggleGuard?.addEventListener("change", () => {
      vibrate(25);
      sendWS("guard:toggle", { enabled: toggleGuard.checked });
      showToast(`CCTV Stealth Guard ${toggleGuard.checked ? "Activated" : "Deactivated"}`, "info");
    });

    // 7. Intruder Modal extra buttons
    document.getElementById("btn-intruder-lock")?.addEventListener("click", () => {
      vibrate(40);
      sendWS("system:action", { action: "lock" });
      showToast("🔒 PC Workstation Locked", "info");
    });

    document.getElementById("btn-intruder-dismiss")?.addEventListener("click", () => {
      vibrate(30);
      sendWS("sentry:disarm");
      stopPhoneSirenTone();
      document.getElementById("modal-intruder-alert")?.classList.add("hidden");
      showToast("🟢 Sentry Disarmed & Alarm Dismissed", "info");
    });
  }

  function startSentryArmingCountdown(seconds) {
    const card = document.getElementById("sentry-card");
    const badge = document.getElementById("sentry-status-badge");
    const cd = document.getElementById("sentry-countdown");
    const btn = document.getElementById("btn-toggle-sentry");
    const btnTxt = document.getElementById("btn-sentry-text");
    const desc = document.getElementById("sentry-desc-text");

    if (card) {
      card.className = "app-card sentry-hero-card arming";
    }
    if (badge) {
      badge.className = "sentry-badge badge-arming";
      badge.textContent = "ARMING...";
    }
    if (cd) {
      cd.classList.remove("hidden");
      cd.textContent = `${seconds}s`;
    }
    if (btn) {
      btn.className = "btn-sentry-main btn-sentry-disarm";
    }
    if (btnTxt) {
      btnTxt.textContent = "CANCEL ARMING";
    }
    if (desc) {
      desc.textContent = `Arming in progress (${seconds}s). Step away from your laptop now.`;
    }

    if (sentryCountdownInterval) clearInterval(sentryCountdownInterval);
    let left = seconds;
    sentryCountdownInterval = setInterval(() => {
      left--;
      if (left > 0) {
        if (cd) cd.textContent = `${left}s`;
        if (desc) desc.textContent = `Arming in ${left}s... Step away from your laptop table.`;
      } else {
        clearInterval(sentryCountdownInterval);
        sentryCountdownInterval = null;
        if (cd) cd.classList.add("hidden");
        if (!isSentryRinging) {
          updateSentryUI({ active: true, ringing: false, is_grace: false });
        }
      }
    }, 1000);
  }

  function updateSentryUI(data) {
    isSentryArmed = !!data.active;
    isSentryRinging = !!data.ringing;

    const card = document.getElementById("sentry-card");
    const badge = document.getElementById("sentry-status-badge");
    const cd = document.getElementById("sentry-countdown");
    const btn = document.getElementById("btn-toggle-sentry");
    const btnTxt = document.getElementById("btn-sentry-text");
    const desc = document.getElementById("sentry-desc-text");
    const powerVal = document.getElementById("tripwire-power-val");

    if (powerVal && data.initial_plugged !== undefined) {
      powerVal.textContent = data.initial_plugged ? "AC Connected (Tripwire Set)" : "Battery Mode";
    }

    if (!data.active) {
      // Disarmed State
      if (sentryCountdownInterval) {
        clearInterval(sentryCountdownInterval);
        sentryCountdownInterval = null;
      }
      stopPhoneSirenTone();
      document.getElementById("modal-intruder-alert")?.classList.add("hidden");
      if (card) card.className = "app-card sentry-hero-card";
      if (badge) {
        badge.className = "sentry-badge";
        badge.textContent = "DISARMED";
      }
      if (cd) cd.classList.add("hidden");
      if (btn) btn.className = "btn-sentry-main btn-sentry-arm";
      if (btnTxt) btnTxt.textContent = "ARM SENTRY (10s)";
      if (desc) desc.textContent = "Cafe & Library Vault. Sounds 100% siren & alerts phone if laptop is moved or charger is unplugged.";
    } else if (data.ringing) {
      // Alarm Triggered State
      if (card) card.className = "app-card sentry-hero-card triggered";
      if (badge) {
        badge.className = "sentry-badge badge-alert";
        badge.textContent = "🚨 ALARM TRIGGERED!";
      }
      if (cd) cd.classList.add("hidden");
      if (btn) btn.className = "btn-sentry-main btn-sentry-disarm";
      if (btnTxt) btnTxt.textContent = "🟢 STOP SIREN & DISARM";
      if (desc) desc.textContent = "🚨 THEFT TRIPWIRE BREACHED! Laptop is sounding 100% police siren!";
    } else if (data.is_grace) {
      // Arming Countdown State
      if (!sentryCountdownInterval) {
        startSentryArmingCountdown(data.grace_remaining || 10);
      }
    } else {
      // Fully Armed State
      if (sentryCountdownInterval) {
        clearInterval(sentryCountdownInterval);
        sentryCountdownInterval = null;
      }
      if (card) card.className = "app-card sentry-hero-card armed";
      if (badge) {
        badge.className = "sentry-badge badge-armed";
        badge.textContent = "🟢 ARMED & SECURED";
      }
      if (cd) cd.classList.add("hidden");
      if (btn) btn.className = "btn-sentry-main btn-sentry-disarm";
      if (btnTxt) btnTxt.textContent = "🟢 DISARM SENTRY";
      if (desc) desc.textContent = "🛡️ Laptop sensors are actively guarded. Charger unplug or mouse motion will trigger 100% siren!";
    }
  }

  function handleSentryTriggered(data) {
    vibrate([400, 200, 400, 200, 800]);
    startPhoneSirenTone();

    const modal = document.getElementById("modal-intruder-alert");
    const title = document.getElementById("intruder-modal-title");
    const sub = document.getElementById("intruder-modal-sub");
    const img = document.getElementById("intruder-modal-img");
    const timeEl = document.getElementById("intruder-time-text");

    if (title) title.textContent = "🚨 SENTRY TRIPWIRE BREACHED!";
    if (sub) sub.textContent = data.reason || "Laptop was physically touched or charger was unplugged!";
    if (img && data.photo) img.src = data.photo;
    if (timeEl) timeEl.textContent = `Time: ${data.time || "Just now"} • ${data.reason || ""}`;
    if (modal) modal.classList.remove("hidden");

    updateSentryUI({ active: true, ringing: true });
    updateIntruderPreview(data);
  }

  function handleIntruderAlert(data) {
    vibrate([200, 100, 200, 100, 400]);
    const modal = document.getElementById("modal-intruder-alert");
    const img = document.getElementById("intruder-modal-img");
    const timeEl = document.getElementById("intruder-time-text");

    if (img && data.photo) img.src = data.photo;
    if (timeEl) timeEl.textContent = `Time: ${data.time || "Just now"} (${data.reason || "Physical movement detected"})`;
    if (modal) modal.classList.remove("hidden");

    updateIntruderPreview(data);
  }

  function updateIntruderPreview(data) {
    const box = document.getElementById("intruder-preview-box");
    const img = document.getElementById("intruder-preview-img");
    const timeEl = document.getElementById("intruder-preview-time");
    if (box && img && data.photo) {
      img.src = data.photo;
      if (timeEl) timeEl.textContent = data.time || "Just now";
      box.classList.remove("hidden");
    }
  }

  function renderSecurityLogs(logs) {
    const container = document.getElementById("sec-logs-container");
    if (!container) return;
    if (!logs || logs.length === 0) {
      container.innerHTML = `<div class="loading-text" style="color: var(--text-dim);">No security events recorded yet.</div>`;
      return;
    }
    container.innerHTML = logs.slice(0, 15).map(log => `
      <div class="sec-log-row">
        <div>
          <span class="sec-log-action">${log.event || log.action || "EVENT"}</span>
          <p style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">${log.detail || log.message || ""}</p>
        </div>
        <span class="sec-log-time">${log.time || log.timestamp || ""}</span>
      </div>
    `).join("");
  }

  // --- 4. Auto-Updater Controller & Notification ---
  function setupAutoUpdater() {
    const banner = document.getElementById("update-alert-banner");
    const bannerText = document.getElementById("update-banner-text");
    const btnApply = document.getElementById("btn-apply-update");
    const btnDismiss = document.getElementById("btn-dismiss-update");

    btnDismiss?.addEventListener("click", () => {
      vibrate(10);
      banner?.classList.add("hidden");
    });

    btnApply?.addEventListener("click", () => {
      vibrate(25);
      if (confirm("PC par latest update download karke restart karein?")) {
        btnApply.disabled = true;
        btnApply.textContent = "Updating...";
        sendWS("update:apply");
        showToast("Downloading update on PC. PC will restart automatically...", "info");
      }
    });

    window.renderUpdateBanner = (info) => {
      if (info && info.has_update) {
        if (bannerText) {
          bannerText.textContent = `🚀 New Update Available (${info.latest_version})!`;
        }
        banner?.classList.remove("hidden");
      }
    };
  }

  // --- 5. Live Hardware Monitor HUD Loop (2-sec auto refresh) ---
  let hudInterval = null;
  function setupLiveHUDLoop() {
    if (hudInterval) clearInterval(hudInterval);
    hudInterval = setInterval(() => {
      if (isConnected && (activeTab === "system" || activeTab === "trackpad")) {
        sendWS("system:stats");
      }
    }, 2000);
  }

  // --- 6. PC Media Server & Instant Local Streaming Player ---
  let cachedMediaItems = [];
  let currentActiveMediaFilter = "all";
  let currentSelectedFolder = null;
  let activePlayingMedia = null;

  function setupMediaServer() {
    const refreshBtn = document.getElementById("btn-refresh-media");
    const searchInput = document.getElementById("media-search-input");
    const filterPills = document.querySelectorAll(".media-filter-pill");
    const closePlayerBtn = document.getElementById("btn-close-media-player");
    const playOnPcBtn = document.getElementById("btn-play-on-pc");
    const playerModal = document.getElementById("modal-media-player");

    refreshBtn?.addEventListener("click", () => {
      vibrate(15);
      loadMediaLibrary(currentActiveMediaFilter, currentSelectedFolder);
    });

    searchInput?.addEventListener("input", (e) => {
      filterAndRenderMediaItems(e.target.value.toLowerCase().trim());
    });

    filterPills.forEach((pill) => {
      pill.addEventListener("click", () => {
        vibrate(10);
        filterPills.forEach((p) => p.classList.remove("active"));
        pill.classList.add("active");
        currentActiveMediaFilter = pill.dataset.mediaType || "all";
        loadMediaLibrary(currentActiveMediaFilter, currentSelectedFolder);
      });
    });

    closePlayerBtn?.addEventListener("click", () => {
      closeMediaPlayer();
    });

    playerModal?.addEventListener("click", (e) => {
      if (e.target === playerModal) {
        closeMediaPlayer();
      }
    });

    playOnPcBtn?.addEventListener("click", async () => {
      vibrate(20);
      if (!activePlayingMedia) return;
      playOnPcBtn.disabled = true;
      playOnPcBtn.textContent = "Launching on PC...";
      try {
        const res = await fetch("/api/media/play_pc", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Session-Token": sessionToken,
          },
          body: JSON.stringify({ path: activePlayingMedia.path }),
        });
        const json = await res.json();
        if (json.success) {
          showToast(`🖥️ Playing on PC: ${json.filename}`, "success");
        } else {
          showToast(`⚠️ ${json.error || "Failed to launch on PC"}`, "error");
        }
      } catch (err) {
        showToast(`Error: ${err.message}`, "error");
      } finally {
        playOnPcBtn.disabled = false;
        playOnPcBtn.innerHTML = `<span>🖥️ Play on PC Screen</span>`;
      }
    });
  }

  function closeMediaPlayer() {
    const playerModal = document.getElementById("modal-media-player");
    const videoEl = document.getElementById("media-html5-video");
    const audioEl = document.getElementById("media-html5-audio");
    if (videoEl) {
      videoEl.pause();
      videoEl.src = "";
    }
    if (audioEl) {
      audioEl.pause();
      audioEl.src = "";
    }
    playerModal?.classList.add("hidden");
    activePlayingMedia = null;
  }

  async function loadMediaLibrary(category = "all", targetFolder = null) {
    const container = document.getElementById("media-grid-container");
    const countsText = document.getElementById("media-counts-text");
    if (container) {
      container.innerHTML = `<div class="loading-text" style="grid-column: 1 / -1; padding: 24px 0;"><span class="spinner" style="margin: 0 auto 8px auto;"></span>Scanning PC media files...</div>`;
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 8000);

    try {
      const q = new URLSearchParams({ category, token: sessionToken || "" });
      if (targetFolder) q.append("path", targetFolder);

      const res = await fetch(`/api/media/library?${q.toString()}`, {
        headers: { "X-Session-Token": sessionToken || "" },
        signal: controller.signal
      });
      clearTimeout(timeoutId);
      const data = await res.json();

      if (!data.success) {
        if (container) {
          container.innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1; padding: 32px 16px; text-align: center;">
              <div style="font-size: 32px; margin-bottom: 8px;">⚠️</div>
              <div style="font-size: 13px; font-weight: 700; color: var(--red); margin-bottom: 4px;">${data.error || "Could not load media"}</div>
              <button class="btn btn-sm btn-tool" style="margin: 8px auto 0 auto;" onclick="loadMediaLibrary()">🔄 Try Again</button>
            </div>
          `;
        }
        return;
      }

      cachedMediaItems = data.items || [];

      if (countsText && data.counts) {
        countsText.textContent = `Found ${data.counts.video || 0} Videos • ${data.counts.audio || 0} Tracks • ${data.counts.image || 0} Photos`;
      }

      renderMediaFolders(data.folders || []);
      filterAndRenderMediaItems();
    } catch (err) {
      clearTimeout(timeoutId);
      if (container) {
        const isTimeout = err.name === "AbortError";
        container.innerHTML = `
          <div class="empty-state" style="grid-column: 1 / -1; padding: 32px 16px; text-align: center;">
            <div style="font-size: 32px; margin-bottom: 8px;">⚠️</div>
            <div style="font-size: 13px; font-weight: 700; color: var(--red); margin-bottom: 4px;">${isTimeout ? "Scan timed out" : "Unable to reach PC Media Server"}</div>
            <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 12px;">${isTimeout ? "Check PC load and try again" : err.message}</div>
            <button class="btn btn-sm btn-tool" style="margin: 0 auto;" onclick="loadMediaLibrary()">🔄 Retry Scan</button>
          </div>
        `;
      }
    }
  }

  function renderMediaFolders(folders) {
    const container = document.getElementById("media-folders-chips");
    if (!container) return;
    const allActive = !currentSelectedFolder ? "active" : "";
    const allChip = `<button class="btn-folder-tag ${allActive}" onclick="window.filterMediaFolder(null)">📁 All Folders</button>`;
    const chips = folders.map((f) => {
      const isAct = currentSelectedFolder === f.path ? "active" : "";
      return `<button class="btn-folder-tag ${isAct}" onclick="window.filterMediaFolder('${encodeURIComponent(f.path)}')">${f.icon || "📁"} ${escapeHtml(f.name)}</button>`;
    }).join("");
    container.innerHTML = allChip + chips;
  }

  window.filterMediaFolder = function (encodedPath) {
    vibrate(10);
    currentSelectedFolder = encodedPath ? decodeURIComponent(encodedPath) : null;
    loadMediaLibrary(currentActiveMediaFilter, currentSelectedFolder);
  };

  function filterAndRenderMediaItems(searchQuery = "") {
    const container = document.getElementById("media-grid-container");
    if (!container) return;

    let items = cachedMediaItems;
    if (searchQuery) {
      items = items.filter(
        (it) => it.name.toLowerCase().includes(searchQuery) || it.title.toLowerCase().includes(searchQuery)
      );
    }

    if (items.length === 0) {
      container.innerHTML = `
        <div style="grid-column: 1 / -1; text-align: center; padding: 32px 16px; color: var(--text-dim);">
          <div style="font-size: 36px; margin-bottom: 8px;">🎬</div>
          <p style="font-size: 13px; font-weight: 700; color: #fff;">No media files found</p>
          <p style="font-size: 11px; margin-top: 4px;">Place .mp4, .mkv, .mp3 or photos in Videos, Music or Downloads folder</p>
        </div>
      `;
      return;
    }

    container.innerHTML = items.map((item) => {
      const isVideo = item.type === "video";
      const isAudio = item.type === "audio";
      const isImage = item.type === "image";

      const typeIcon = isVideo ? "🎬" : isAudio ? "🎵" : "🖼️";
      const badgeColor = isVideo ? "var(--cyan)" : isAudio ? "var(--purple)" : "var(--green)";
      const thumbUrl = `/api/media/thumbnail?path=${encodeURIComponent(item.path)}&token=${encodeURIComponent(sessionToken || "")}`;

      return `
        <div class="media-card" onclick="window.openMediaItem('${item.id}')" title="Play ${escapeHtml(item.name)}">
          <div class="media-thumb-wrap">
            <img src="${thumbUrl}" class="media-thumb-img" alt="${escapeHtml(item.title)}" loading="lazy" onerror="this.onerror=null; this.src=''; this.style.display='none'; this.nextElementSibling.style.display='flex';">
            <div style="display:none; width: 100%; height: 100%; align-items: center; justify-content: center; font-size: 32px; opacity: 0.35;">${typeIcon}</div>
            <span class="media-type-badge" style="color: ${badgeColor};">${item.ext}</span>
            <div class="media-play-overlay">
              <span class="media-play-btn">${isVideo ? "▶" : isAudio ? "🎵" : "🔍"}</span>
            </div>
          </div>
          <div class="media-card-body">
            <span class="media-title" title="${escapeHtml(item.name)}">${escapeHtml(item.title || item.name)}</span>
            <div class="media-meta">
              <span>${item.size_formatted}</span>
              <span>${escapeHtml(item.folder)}</span>
            </div>
          </div>
        </div>
      `;
    }).join("");
  }

  window.openMediaItem = function (itemId) {
    vibrate(15);
    const item = cachedMediaItems.find((it) => it.id === itemId);
    if (!item) return;

    activePlayingMedia = item;
    const modal = document.getElementById("modal-media-player");
    const titleEl = document.getElementById("player-media-title");
    const subEl = document.getElementById("player-media-sub");
    const iconEl = document.getElementById("player-media-icon");
    const downloadBtn = document.getElementById("btn-download-media-direct");

    const videoWrap = document.getElementById("player-video-viewport");
    const audioWrap = document.getElementById("player-audio-viewport");
    const imageWrap = document.getElementById("player-image-viewport");

    const videoEl = document.getElementById("media-html5-video");
    const audioEl = document.getElementById("media-html5-audio");
    const imgEl = document.getElementById("media-lightbox-img");

    if (titleEl) titleEl.textContent = item.name;
    if (subEl) subEl.textContent = `${item.size_formatted} • ${item.ext} • ${item.folder}`;
    if (iconEl) iconEl.textContent = item.type === "video" ? "🎬" : item.type === "audio" ? "🎵" : "🖼️";

    const streamUrl = `/api/media/stream?path=${encodeURIComponent(item.path)}&token=${encodeURIComponent(sessionToken || "")}`;
    if (downloadBtn) downloadBtn.href = streamUrl;

    // Reset viewports
    videoWrap?.classList.add("hidden");
    audioWrap?.classList.add("hidden");
    imageWrap?.classList.add("hidden");

    if (videoEl) { videoEl.pause(); videoEl.src = ""; }
    if (audioEl) { audioEl.pause(); audioEl.src = ""; }

    if (item.type === "video") {
      videoWrap?.classList.remove("hidden");
      if (videoEl) {
        videoEl.src = streamUrl;
        videoEl.play().catch(() => {});
      }
    } else if (item.type === "audio") {
      audioWrap?.classList.remove("hidden");
      if (audioEl) {
        audioEl.src = streamUrl;
        audioEl.play().catch(() => {});
      }
    } else if (item.type === "image") {
      imageWrap?.classList.remove("hidden");
      if (imgEl) imgEl.src = streamUrl;
    }

    modal?.classList.remove("hidden");
  };


  // --- 7. Voice Assistant & Real-Time Speech-to-PC Dictation ---
  let speechRecognizer = null;
  let isVoiceListening = false;

  function setupVoiceAssistant() {
    const voiceBtn = document.getElementById("btn-voice-control");
    const voiceModal = document.getElementById("modal-voice-assistant");
    const closeBtn = document.getElementById("btn-close-voice-modal");
    const toggleRecBtn = document.getElementById("btn-toggle-voice-recording");
    const statusLabel = document.getElementById("voice-status-label");
    const transcriptBox = document.getElementById("voice-transcript-box");
    const wave = document.getElementById("voice-mic-wave");

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      if (voiceBtn) {
        voiceBtn.title = "Voice recognition not supported in this browser";
        voiceBtn.style.opacity = "0.5";
      }
    }

    voiceBtn?.addEventListener("click", () => {
      vibrate(15);
      if (!SpeechRecognition) {
        showToast("⚠️ Voice recognition is not supported in this browser. Use Chrome or Safari.", "error");
        return;
      }
      voiceModal?.classList.remove("hidden");
      startVoiceListening();
    });

    closeBtn?.addEventListener("click", () => {
      stopVoiceListening();
      voiceModal?.classList.add("hidden");
    });

    voiceModal?.addEventListener("click", (e) => {
      if (e.target === voiceModal) {
        stopVoiceListening();
        voiceModal.classList.add("hidden");
      }
    });

    toggleRecBtn?.addEventListener("click", () => {
      vibrate(15);
      if (isVoiceListening) {
        stopVoiceListening();
      } else {
        startVoiceListening();
      }
    });

    function startVoiceListening() {
      if (!SpeechRecognition) return;
      try {
        if (speechRecognizer) {
          try { speechRecognizer.abort(); } catch (e) {}
        }
        speechRecognizer = new SpeechRecognition();
        speechRecognizer.continuous = true;
        speechRecognizer.interimResults = true;
        speechRecognizer.lang = "en-IN";

        speechRecognizer.onstart = () => {
          isVoiceListening = true;
          if (statusLabel) statusLabel.textContent = "🎙️ Listening... Speak now";
          if (transcriptBox) transcriptBox.textContent = "Listening to speech...";
          if (wave) {
            wave.style.opacity = "1";
            wave.classList.add("pulse-wave-anim");
          }
          if (toggleRecBtn) toggleRecBtn.style.background = "linear-gradient(135deg, #ef4444, #f43f5e)";
        };

        speechRecognizer.onresult = (e) => {
          let interim = "";
          let finalTranscript = "";
          for (let i = e.resultIndex; i < e.results.length; ++i) {
            if (e.results[i].isFinal) {
              finalTranscript += e.results[i][0].transcript;
            } else {
              interim += e.results[i][0].transcript;
            }
          }
          const text = finalTranscript || interim;
          if (transcriptBox && text) {
            transcriptBox.textContent = `"${text.trim()}"`;
          }
          if (finalTranscript) {
            handleVoiceCommand(finalTranscript.trim());
          }
        };

        speechRecognizer.onerror = (e) => {
          console.warn("[Speech] Error:", e.error);
          if (e.error === "not-allowed") {
            if (statusLabel) statusLabel.textContent = "⚠️ Microphone permission denied";
          } else {
            if (statusLabel) statusLabel.textContent = `Speech error: ${e.error}`;
          }
          stopVoiceListening();
        };

        speechRecognizer.onend = () => {
          if (isVoiceListening) {
            try { speechRecognizer.start(); } catch (err) { stopVoiceListening(); }
          }
        };

        speechRecognizer.start();
      } catch (err) {
        console.error("[Speech Start Error]:", err);
        stopVoiceListening();
      }
    }

    function stopVoiceListening() {
      isVoiceListening = false;
      if (speechRecognizer) {
        try { speechRecognizer.stop(); } catch (e) {}
      }
      if (statusLabel) statusLabel.textContent = "Tap Mic to Speak";
      if (wave) {
        wave.style.opacity = "0";
        wave.classList.remove("pulse-wave-anim");
      }
      if (toggleRecBtn) toggleRecBtn.style.background = "linear-gradient(135deg, #0ea5e9, #38bdf8)";
    }

    function handleVoiceCommand(raw) {
      vibrate([20, 20]);
      const lower = raw.toLowerCase().trim();

      if (lower.includes("open chrome") || lower.includes("open browser") || lower.includes("chrome kholo")) {
        sendWS("app:launch", { app_key: "chrome" });
        showVoiceFeedback("🚀 Opened Google Chrome");
      } else if (lower.includes("open youtube") || lower.includes("youtube kholo") || lower.includes("play youtube")) {
        sendWS("app:launch", { app_key: "youtube" });
        showVoiceFeedback("▶️ Opened YouTube");
      } else if (lower.includes("open vscode") || lower.includes("open code") || lower.includes("code kholo")) {
        sendWS("app:launch", { app_key: "vscode" });
        showVoiceFeedback("💻 Opened VS Code");
      } else if (lower.includes("open notepad") || lower.includes("notepad kholo")) {
        sendWS("app:launch", { app_key: "notepad" });
        showVoiceFeedback("📝 Opened Notepad");
      } else if (lower.includes("open calculator") || lower.includes("calculator kholo") || lower.includes("calc")) {
        sendWS("app:launch", { app_key: "calc" });
        showVoiceFeedback("🔢 Opened Calculator");
      } else if (lower.includes("open files") || lower.includes("open explorer") || lower.includes("explorer kholo")) {
        sendWS("app:launch", { app_key: "explorer" });
        showVoiceFeedback("📁 Opened File Explorer");
      } else if (lower.includes("task manager") || lower.includes("taskmgr")) {
        sendWS("app:launch", { app_key: "taskmgr" });
        showVoiceFeedback("📊 Opened Task Manager");
      } else if (lower.includes("lock pc") || lower.includes("lock computer") || lower.includes("pc lock")) {
        sendWS("system:action", { action: "lock" });
        showVoiceFeedback("🔒 Locked PC");
      } else if (lower.includes("mute") || lower.includes("unmute") || lower.includes("awaaz band")) {
        sendWS("keyboard:shortcut", { shortcut: "volume_mute" });
        showVoiceFeedback("🔇 Toggled Mute");
      } else if (lower.includes("volume up") || lower.includes("awaaz badhao") || lower.includes("increase volume")) {
        sendWS("keyboard:shortcut", { shortcut: "volume_up" });
        sendWS("keyboard:shortcut", { shortcut: "volume_up" });
        showVoiceFeedback("🔊 Volume Up");
      } else if (lower.includes("volume down") || lower.includes("awaaz kam") || lower.includes("decrease volume")) {
        sendWS("keyboard:shortcut", { shortcut: "volume_down" });
        sendWS("keyboard:shortcut", { shortcut: "volume_down" });
        showVoiceFeedback("🔉 Volume Down");
      } else if (lower.includes("next song") || lower.includes("next track") || lower.includes("agla gana")) {
        sendWS("keyboard:shortcut", { shortcut: "media_next" });
        showVoiceFeedback("⏭️ Next Track");
      } else if (lower.includes("play") || lower.includes("pause") || lower.includes("stop music") || lower.includes("gana roko")) {
        sendWS("keyboard:shortcut", { shortcut: "media_play_pause" });
        showVoiceFeedback("⏯️ Play / Pause");
      } else if (lower.includes("boss key") || lower.includes("panic")) {
        sendWS("system:action", { action: "panic" });
        showVoiceFeedback("🚨 Boss Key Triggered");
      } else if (lower.includes("screenshot") || lower.includes("take screenshot")) {
        sendWS("keyboard:shortcut", { shortcut: "win+printscreen" });
        showVoiceFeedback("📸 Screenshot Captured");
      } else {
        // Voice Dictation: Type directly into active PC text area!
        sendWS("keyboard:type", { text: raw + " " });
        showVoiceFeedback(`✍️ Typed to PC: "${raw}"`);
      }
    }

    function showVoiceFeedback(msg) {
      if (statusLabel) {
        statusLabel.textContent = msg;
        statusLabel.style.color = "var(--cyan)";
      }
      showToast(msg, "info");
      setTimeout(() => {
        if (statusLabel && isVoiceListening) {
          statusLabel.textContent = "🎙️ Listening... Speak now";
          statusLabel.style.color = "var(--text-main)";
        }
      }, 2200);
    }
  }

})();
