// Theme Toggle - Modo Diurno/Nocturno + Stars animation
document.addEventListener('DOMContentLoaded', () => {
    const body = document.body;

    // Helper: find all relevant checkbox toggles on the page
    const switches = Array.from(document.querySelectorAll('.theme-switch-wrapper input[type="checkbox"], .theme-switch input[type="checkbox"], input#checkbox, input#themeCheck'));
    const themeLabels = Array.from(document.querySelectorAll('.theme-label'));

    // Ensure there's at least one checkbox reference (some pages use different ids)
    function setAllSwitches(checked) {
        switches.forEach(s => { s.checked = checked; });
    }

    // Update label text where present
    function updateLabels(isNight) {
        themeLabels.forEach(lbl => {
            lbl.textContent = isNight ? 'Modo Diurno' : 'Modo Nocturno';
        });
    }

    // Persisted preference
    const savedTheme = localStorage.getItem('theme');
    const initialNight = savedTheme === 'night';
    if (initialNight) {
        body.classList.add('night-mode');
    }
    setAllSwitches(initialNight);
    updateLabels(initialNight);

    // Stars animation manager
    const Starfield = (function(){
        let overlay; let stars = []; let running = false; let rafId = null; let lastTs = 0; let skyLimitRatio = 0.75;

        function injectStyles(){
            if (document.getElementById('starfield-styles')) return;
            const css = `
                .stars-overlay{position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;overflow:hidden;z-index:1;opacity:0;transition:opacity 0.5s ease}
                body.night-mode .stars-overlay{opacity:1}
                .stars-overlay .star{position:absolute;border-radius:50%;background:radial-gradient(circle, #fff 0%, rgba(255,255,255,0.8) 60%, rgba(255,255,255,0.2) 100%);box-shadow:0 0 6px rgba(255,255,255,0.9);opacity:0.95}
            `;
            const style = document.createElement('style');
            style.id = 'starfield-styles';
            style.appendChild(document.createTextNode(css));
            document.head.appendChild(style);
        }

        function ensureOverlay(){
            const bg = document.querySelector('.background') || document.body;
            overlay = bg.querySelector('.stars-overlay');
            if (!overlay) {
                overlay = document.createElement('div');
                overlay.className = 'stars-overlay';
                // insert as first child after grid-overlay if present
                const grid = bg.querySelector('.grid-overlay');
                if (grid && grid.parentNode) grid.parentNode.insertBefore(overlay, grid.nextSibling);
                else bg.insertBefore(overlay, bg.firstChild);
            }
            overlay.style.position = 'absolute';
            overlay.style.top = '0';
            overlay.style.left = '0';
            overlay.style.width = '100%';
            overlay.style.height = '100%';
        }

        function createStars(count){
            clearStars();
            const rect = getBackgroundRect();
            const skyH = Math.max(20, Math.floor(rect.height * skyLimitRatio));
            const width = rect.width;
            for(let i=0;i<count;i++){
                const el = document.createElement('div');
                el.className = 'star';
                const size = Math.random()*4 + 0.8; // 0.8 - 4.8 px
                const x = Math.random() * width;
                const y = Math.random() * skyH;
                el.style.width = `${size}px`;
                el.style.height = `${size}px`;
                el.style.left = `0px`;
                el.style.top = `0px`;
                el.style.transform = `translate(${x}px, ${y}px)`;
                el.style.willChange = 'transform';
                overlay.appendChild(el);
                stars.push({el,x,y,size,vx:(Math.random()*40-10), vy:(Math.random()*10-5)}); // vx in px/s
            }
        }

        function clearStars(){
            if (!overlay) return;
            stars.forEach(s=>{ if(s.el && s.el.parentNode) s.el.parentNode.removeChild(s.el); });
            stars = [];
        }

        function getBackgroundRect(){
            const bg = document.querySelector('.background') || document.body;
            return bg.getBoundingClientRect();
        }

        function animate(ts){
            if (!lastTs) lastTs = ts; const dt = Math.min(0.05, (ts - lastTs)/1000); lastTs = ts; // cap dt
            const rect = getBackgroundRect();
            const skyH = Math.max(20, Math.floor(rect.height * skyLimitRatio));
            const width = rect.width;
            for(const s of stars){
                s.x += s.vx * dt;
                s.y += s.vy * dt;
                // gentle vertical drift
                s.vy += (Math.random()-0.5)*2*dt;
                // Keep within sky bounds
                if (s.y < 2) { s.y = 2; s.vy = Math.abs(s.vy); }
                if (s.y > skyH - s.size) { s.y = skyH - s.size; s.vy = -Math.abs(s.vy); }
                // Wrap horizontally
                if (s.x < -10) s.x = width + 10;
                if (s.x > width + 10) s.x = -10;
                s.el.style.transform = `translate(${s.x}px, ${s.y}px)`;
            }
            rafId = running ? window.requestAnimationFrame(animate) : null;
        }

        function start(){
            if (running) return; running = true; lastTs = 0;
            injectStyles(); ensureOverlay();
            const rect = getBackgroundRect();
            const count = Math.max(20, Math.floor(rect.width / 30));
            if (stars.length === 0) createStars(count);
            rafId = window.requestAnimationFrame(animate);
        }

        function stop(){
            running = false; if (rafId) { window.cancelAnimationFrame(rafId); rafId = null; }
            lastTs = 0;
        }

        function resize(){
            const rect = getBackgroundRect();
            const desired = Math.max(20, Math.floor(rect.width / 30));
            if (desired !== stars.length){ createStars(desired); }
            // clamp stars inside sky
            const skyH = Math.max(20, Math.floor(rect.height * skyLimitRatio));
            for(const s of stars){ if (s.y > skyH - s.size) s.y = Math.max(2, skyH - s.size - 1); }
        }

        return {start, stop, resize, ensureOverlay};
    })();

    // Start/stop animation based on current theme
    function applyTheme(isNight){
        if (isNight) { Starfield.ensureOverlay(); Starfield.start(); }
        else { Starfield.stop(); }
    }

    applyTheme(initialNight);

    // Wire up switches
    switches.forEach(sw => {
        sw.addEventListener('change', (e) => {
            const isNight = !!e.target.checked;
            setAllSwitches(isNight);
            if (isNight) body.classList.add('night-mode'); else body.classList.remove('night-mode');
            updateLabels(isNight);
            localStorage.setItem('theme', isNight ? 'night' : 'day');
            applyTheme(isNight);
        });
    });

    // Window resize handler to recompute star positions/counts
    window.addEventListener('resize', () => { try{ Starfield.resize(); }catch(e){} });
});