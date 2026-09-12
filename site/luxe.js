/* Cabo Transportation Concierge — motion + the interactive parts the original Vue app handled. */
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const WA = "520000000000"; // TODO: client's WhatsApp

  /* ---------- Scroll progress + header ---------- */
  const bar = document.createElement("div");
  bar.className = "ctc-progress";
  document.body.appendChild(bar);
  const header = $("header.fixed");
  const onScroll = () => {
    const max = document.documentElement.scrollHeight - innerHeight;
    bar.style.transform = `scaleX(${max > 0 ? scrollY / max : 0})`;
    header && header.classList.toggle("ctc-scrolled", scrollY > 40);
  };
  addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  /* ---------- Hero entrance ---------- */
  const hero = $(".ctc-hero-copy");
  if (hero) {
    const h1 = $("h1", hero);
    if (h1 && !reduce) {
      const words = h1.textContent.trim().split(/\s+/);
      h1.innerHTML = words.map((w, i) => `<span class="ctc-word" style="animation-delay:${0.25 + i * 0.09}s">${w}</span>`).join(" ");
    }
    $$(".kick, .lede, .cta, .legal", hero).forEach((el, i) => {
      el.classList.add("ctc-fade-in");
      el.style.animationDelay = `${(i === 0 ? 0.05 : 0.7 + i * 0.15)}s`;
    });
  }

  /* ---------- Hero promo video ---------- */
  const heroVideo = $(".ctc-hero-video");
  if (heroVideo && reduce) { heroVideo.removeAttribute("autoplay"); heroVideo.pause(); }

  /* ---------- Mobile menu ---------- */
  const menuBtn = $('[aria-label="Open main menu"]');
  const menu = $('[role="dialog"][aria-label="Mobile menu"]');
  if (menuBtn && menu) {
    menuBtn.addEventListener("click", () => {
      const open = menu.style.display === "none";
      menu.style.display = open ? "" : "none";
      menuBtn.setAttribute("aria-expanded", open);
      document.body.classList.toggle("ctc-mobile-open", open);
    });
    $$("a", menu).forEach((a) => a.addEventListener("click", () => { menu.style.display = "none"; document.body.classList.remove("ctc-mobile-open"); }));
  }

  /* ---------- Desktop dropdowns (Services / Tours), built from the mobile menu lists ---------- */
  const mnav = menu && $('nav[aria-label="Mobile navigation"]', menu);
  if (mnav) {
    const groups = {};
    $$(":scope > div", mnav).forEach((g) => {
      const label = g.querySelector(":scope > span")?.textContent.trim();
      if (label) groups[label] = g;
    });
    const linkEl = (a) => {
      const c = document.createElement("a");
      c.href = a.getAttribute("href");
      c.setAttribute("role", "menuitem");
      const spans = $$("span", a);
      c.innerHTML = spans.length ? spans[0].innerHTML + (spans[1] ? `<small>${spans[1].innerHTML}</small>` : "") : a.innerHTML.trim();
      return c;
    };
    $$('header nav [id^="headlessui-menu-button"]').forEach((btn) => {
      const g = groups[btn.textContent.trim()];
      if (!g) return;
      const wrap = btn.parentElement;
      const dd = document.createElement("div");
      dd.className = "ctc-dropdown";
      dd.setAttribute("role", "menu");
      const cols = $$("details", g);
      if (cols.length) {
        dd.classList.add("ctc-dropdown--mega");
        cols.forEach((d) => {
          const col = document.createElement("div");
          col.innerHTML = `<h4>${$("summary", d).textContent.trim()}</h4>`;
          $$("a", d).forEach((a) => col.appendChild(linkEl(a)));
          dd.appendChild(col);
        });
        const extra = $$(":scope > a", g);
        if (extra.length) {
          const col = document.createElement("div");
          col.innerHTML = "<h4>Guides</h4>";
          extra.forEach((a) => col.appendChild(linkEl(a)));
          dd.appendChild(col);
        }
      } else {
        $$("a", g).forEach((a) => dd.appendChild(linkEl(a)));
      }
      wrap.appendChild(dd);
      let t;
      const open = (v) => { clearTimeout(t); wrap.classList.toggle("is-open", v); btn.setAttribute("aria-expanded", v); };
      wrap.addEventListener("mouseenter", () => open(true));
      wrap.addEventListener("mouseleave", () => { t = setTimeout(() => open(false), 160); });
      btn.addEventListener("click", () => open(!wrap.classList.contains("is-open")));
      wrap.addEventListener("keydown", (e) => { if (e.key === "Escape") { open(false); btn.focus(); } });
    });
  }

  /* ---------- Booking widget ---------- */
  function initBooking() {
    const form = $("form.flex.flex-col.w-full.bg-white");
    if (!form) return;
    const card = form.parentElement;
    const tabs = $$("button", card.firstElementChild).filter((b) => !form.contains(b));
    const ON = ["bg-[#007a96]", "text-white", "md:border-b-4", "md:-mb-1", "border-[#FFC107]"];
    const OFF = ["bg-brand-ink", "text-slate-400", "border-b-4", "border-transparent", "hover:text-white", "hover:bg-brand-ink-2"];
    const state = { tab: 0, hotel: null, pax: 2, arrive: "", ret: "" };
    const originText = $("#booking-home-origin span.truncate");

    tabs.forEach((b, i) => b.addEventListener("click", () => {
      state.tab = i;
      tabs.forEach((x, j) => { x.classList.remove(...ON, ...OFF); x.classList.add(...(j === i ? ON : OFF)); });
      if (originText) originText.textContent = i < 2 ? "Los Cabos International Airport (SJD)" : "Your hotel or villa";
      const ret = $$("label", form).find((l) => /Return Date/.test(l.textContent));
      if (ret) ret.style.opacity = i === 0 || i === 2 ? "1" : ".4";
      update();
    }));
    if (originText) originText.textContent = "Los Cabos International Airport (SJD)";

    // Destination: hotel search from the ClassVIP hotel list
    const dest = $("#booking-home-destination");
    if (dest && window.CTC_DATA) {
      const label = $("span.text-brand-ink", dest);
      const list = document.createElement("datalist");
      list.id = "ctc-hotels";
      list.innerHTML = window.CTC_DATA.hotels.map(([n]) => `<option value="${n.replace(/"/g, "&quot;")}">`).join("");
      const input = document.createElement("input");
      input.setAttribute("list", "ctc-hotels");
      input.placeholder = "Where are we going?";
      input.setAttribute("aria-label", "Drop-off hotel or villa");
      input.className = "w-full bg-transparent border-0 p-0 text-brand-ink font-semibold text-[18px] lg:text-[20px] focus:outline-none focus:ring-0";
      label.replaceWith(input);
      dest.appendChild(list);
      $$("*", dest).forEach((el) => el.classList.remove("pointer-events-none"));
      dest.addEventListener("click", () => input.focus());
      input.addEventListener("input", () => {
        const hit = window.CTC_DATA.hotels.find(([n]) => n === input.value);
        state.hotel = hit || null;
        update();
      });
    }

    // Dates
    $$('input[readonly][placeholder="Select a date"]', form).forEach((inp, i) => {
      inp.removeAttribute("readonly");
      inp.type = "date";
      inp.min = new Date().toISOString().slice(0, 10);
      inp.addEventListener("change", () => { state[i ? "ret" : "arrive"] = inp.value; update(); });
    });

    // Passengers stepper
    const minus = $$("button", form).find((b) => b.textContent.trim() === "−");
    const plus = $$("button", form).find((b) => b.textContent.trim() === "+");
    const paxOut = minus && [...minus.parentElement.children].find((el) => el !== minus && el !== plus && /^\d+$/.test(el.textContent.trim()));
    const setPax = (d) => { state.pax = Math.max(1, Math.min(14, state.pax + d)); if (paxOut) paxOut.textContent = state.pax; update(); };
    if (minus) minus.addEventListener("click", (e) => { e.preventDefault(); setPax(-1); });
    if (plus) plus.addEventListener("click", (e) => { e.preventDefault(); setPax(1); });
    if (paxOut) paxOut.textContent = state.pax;

    // Estimated total: zone round-trip starting rates from the rate cards on this page
    const ZONE_RT = [160, 160, 185, 195, 205, 230]; // SJC, Puerto Los Cabos, Corridor, CSL, Pacific, East Cape/Pacific North
    const totalEl = $$("*", form).find((el) => el.children.length === 0 && el.textContent.trim() === "---");
    const vehicleEls = $$("*", form).filter((el) => el.children.length === 0 && el.textContent.trim() === "Select a vehicle");
    const submit = $$("button", form).find((b) => /Book My Ride/i.test(b.textContent));
    const hint = $$("*", form).find((el) => el.children.length === 0 && /Select a vehicle to continue/.test(el.textContent));

    function vehicle() { return state.pax <= 6 ? ["Chevrolet Suburban", 1] : state.pax <= 10 ? ["Passenger Van", 1.35] : ["Mercedes Sprinter", 1.6]; }
    function update() {
      const [vName, mult] = vehicle();
      vehicleEls.forEach((el) => (el.textContent = vName));
      if (!state.hotel) { if (totalEl) totalEl.textContent = "---"; if (hint) hint.textContent = "Choose your hotel to see the price."; return; }
      const rt = ZONE_RT[state.hotel[1]] * mult;
      const price = state.tab % 2 === 0 ? rt : Math.round((rt * 0.5625) / 5) * 5;
      if (totalEl) animateNumber(totalEl, Math.round(price));
      if (hint) hint.textContent = `${vName} for ${state.pax} ${state.pax === 1 ? "guest" : "guests"}, tolls and drinks included.`;
    }
    if (submit) submit.addEventListener("click", (e) => {
      e.preventDefault();
      const tab = tabs[state.tab]?.textContent.replace(/\s+/g, " ").trim();
      const msg = `Hi! I'd like to book: ${tab}. Hotel: ${state.hotel ? state.hotel[0] : "(to confirm)"}. Guests: ${state.pax}. Arrival: ${state.arrive || "-"}. Return: ${state.ret || "-"}. Estimated: ${totalEl ? totalEl.textContent : ""}`;
      window.open(`https://wa.me/${WA}?text=${encodeURIComponent(msg)}`, "_blank", "noopener");
    });
    update();
  }

  function animateNumber(el, to) {
    if (reduce) { el.textContent = "$" + to.toLocaleString("en-US") + " USD"; return; }
    const from = +(el.dataset.v || 0);
    el.dataset.v = to;
    const t0 = performance.now();
    const step = (t) => {
      const k = Math.min(1, (t - t0) / 700);
      const e = 1 - Math.pow(1 - k, 3);
      el.textContent = "$" + Math.round(from + (to - from) * e).toLocaleString("en-US") + " USD";
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  /* ---------- Scroll reveals, cards, stars ---------- */
  function initMotion() {
    const sections = $$("main section").filter((s) => !s.contains(hero) && !s.querySelector(".hero-promo-video"));
    sections.forEach((sec) => {
      if (/bg-\[#0a111a\]|bg-brand-ink/.test(sec.className)) sec.classList.add("ctc-aurora");
      $$(".text-h2", sec).forEach((h) => h.classList.add("ctc-line"));
      const blocks = $$("h2, h3, p, blockquote, table, details, article, ul, .grid > *", sec)
        .filter((el) => !el.closest(".ctc-reveal") && !el.closest("form") && el.offsetParent !== null);
      blocks.forEach((el) => {
        const sib = el.parentElement ? [...el.parentElement.children].indexOf(el) : 0;
        el.classList.add("ctc-reveal");
        el.style.setProperty("--d", `${Math.min(sib, 6) * 0.08}s`);
      });
      $$("img", sec).forEach((img) => {
        const w = +img.getAttribute("width") || img.naturalWidth;
        if (w < 200 || img.closest(".ctc-reveal-img")) return;
        const box = img.parentElement;
        box.classList.add("ctc-reveal-img");
        const card = img.closest("a, article");
        if (card) card.classList.add("ctc-card");
      });
      $$("article", sec).forEach((a) => a.classList.add("ctc-card"));
    });
    $$("span.text-brand-gold").forEach((s) => { s.classList.add("ctc-stars"); $$("svg", s).forEach((svg, i) => svg.style.setProperty("--i", i)); });

    const targets = $$(".ctc-reveal, .ctc-reveal-img");
    if (reduce || !("IntersectionObserver" in window)) { targets.forEach((t) => t.classList.add("is-in")); return; }
    const io = new IntersectionObserver((entries) => entries.forEach((en) => {
      if (en.isIntersecting) { en.target.classList.add("is-in"); io.unobserve(en.target); }
    }), { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    targets.forEach((t) => io.observe(t));

    // Gentle parallax on large section photos
    const par = $$(".ctc-reveal-img img").filter((i) => (+i.getAttribute("height") || 0) >= 900);
    addEventListener("scroll", () => {
      par.forEach((img) => {
        const r = img.parentElement.getBoundingClientRect();
        if (r.bottom < 0 || r.top > innerHeight) return;
        const p = (r.top + r.height / 2 - innerHeight / 2) / innerHeight;
        img.style.translate = `0 ${p * -40}px`;
      });
    }, { passive: true });
  }

  /* ---------- AI concierge agent (prototype: answers from the page + hotel/rate data) ---------- */
  function initAgent() {
    const btn = $("[data-ctc-ai]");
    if (!btn) return;
    const norm = (s) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim();
    const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    const RT = [160, 160, 185, 195, 205, 230];
    const ZONES = ["San José del Cabo", "Puerto Los Cabos", "Tourist Corridor", "Cabo San Lucas", "Pacific Side", "Pacific North & East Cape"];
    const faq = $$("details").map((d) => ({ q: $("summary", d)?.textContent.trim() || "", a: [...d.children].filter((c) => c.tagName !== "SUMMARY").map((c) => c.textContent).join(" ").replace(/\s+/g, " ").trim() })).filter((f) => f.q && f.a);
    const hotels = (window.CTC_DATA?.hotels || []).map(([n, z]) => ({ n, z, k: norm(n) }));
    const wa = (text) => `https://wa.me/${WA}?text=${encodeURIComponent(text)}`;

    const panel = document.createElement("section");
    panel.className = "ctc-chat";
    panel.setAttribute("aria-label", "Customer help chat");
    panel.innerHTML = `<header class="ctc-chat-head"><span class="ctc-chat-avatar" aria-hidden="true"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 13v-1a8 8 0 0116 0v1"/><rect x="2.5" y="13" width="4" height="6" rx="1.5"/><rect x="17.5" y="13" width="4" height="6" rx="1.5"/><path d="M19.5 19c0 1.7-1.6 2.5-4 2.5H13"/></svg></span>
      <div><strong>Customer Help</strong><span>Online now. A person can take over on WhatsApp.</span></div><button class="ctc-chat-close" type="button" aria-label="Close chat">×</button></header>
      <div class="ctc-chat-log" aria-live="polite"></div>
      <div class="ctc-chips"><button type="button">Price to my hotel</button><button type="button">Where do I meet my driver?</button><button type="button">Yachts and villas</button><button type="button">Talk to a person</button></div>
      <form class="ctc-chat-form"><label class="sr-only" for="ctc-chat-in">Message</label><input id="ctc-chat-in" autocomplete="off" placeholder="Ask about prices, arrival, yachts..."><button type="submit">Send</button></form>`;
    document.body.appendChild(panel);
    const log = $(".ctc-chat-log", panel);
    const input = $("input", panel);

    const add = (html, who) => { const d = document.createElement("div"); d.className = `ctc-msg ctc-msg--${who}`; d.innerHTML = html; log.appendChild(d); log.scrollTop = log.scrollHeight; return d; };

    function answer(text) {
      const n = norm(text);
      const pax = +(n.match(/(\d+)\s*(people|persons|pax|guests|adults|of us|personas)/)?.[1] || 2);
      const round = /round|both ways|return|ida y vuelta|regreso/.test(n);
      const hotel = hotels.filter((h) => h.k.length > 3 && (n.includes(h.k) || (n.length > 5 && h.k.includes(n)))).sort((a, b) => b.k.length - a.k.length)[0];
      if (hotel) {
        const mult = pax <= 6 ? 1 : pax <= 10 ? 1.35 : 1.6;
        const vehicle = pax <= 6 ? "Chevrolet Suburban" : pax <= 10 ? "passenger van" : "Mercedes Sprinter";
        const rt = RT[hotel.z] * mult;
        const price = round ? rt : Math.round((rt * 0.5625) / 5) * 5;
        return `${esc(hotel.n)} is in our ${ZONES[hotel.z]} zone. For ${pax} ${pax === 1 ? "guest" : "guests"} you ride in a private ${vehicle}, tolls and cold drinks included.
          <div class="ctc-quote"><span><b>$${Math.round(price)}</b> USD ${round ? "round trip" : "one way"}</span><a href="${wa(`Hi! I'd like to book ${round ? "a round trip" : "a one-way transfer"} from SJD to ${hotel.n} for ${pax} guests.`)}" target="_blank" rel="noopener">Book on WhatsApp</a></div>`;
      }
      if (/(price|rate|cost|how much|quote|precio|cuanto)/.test(n)) return "Tell me your hotel and how many guests, for example “Riu Palace, 4 people, round trip”, and I'll give you the price right away.";
      if (/(arriv|land|meet|find|hostess|canopy|terminal|customs|timeshare|llegada)/.test(n)) return `After customs, keep walking past the timeshare desks and exit the terminal. Walk past the taxi drivers, cross the yellow stripes toward the Island Bar, and look for our hostess with the CABO TRANSPORTATION CONCIERGE sign in Canopy 3. <a href="arrival-guide.html">See the arrival guide</a>`;
      if (/(yacht|boat|sail|villa|tour|activit|yate|excursion)/.test(n)) return `We also arrange private yachts, private tours, luxury villas and activities in Cabo San Lucas. <a href="${wa("Hi! I'd like info about yachts, tours, villas or activities.")}" target="_blank" rel="noopener">Message the concierge on WhatsApp</a> with your dates and group size.`;
      if (/(person|human|agent|whatsapp|call|phone|talk|hablar)/.test(n)) return `Of course. <a href="${wa("Hi! I have a question about my Cabo trip.")}" target="_blank" rel="noopener">Open WhatsApp</a> and a person from our team will reply.`;
      const words = n.split(" ").filter((w) => w.length > 3);
      const best = faq.map((f) => ({ f, s: words.filter((w) => norm(f.q + " " + f.a).includes(w)).length })).sort((a, b) => b.s - a.s)[0];
      if (best && best.s >= 2) return `<b>${esc(best.f.q)}</b><br>${esc(best.f.a.length > 420 ? best.f.a.slice(0, 420) + "…" : best.f.a)}`;
      return `I can quote your transfer to any hotel in Los Cabos, explain how to meet your driver at SJD, or help with yachts, tours and villas. What do you need? You can also <a href="${wa("Hi! I have a question.")}" target="_blank" rel="noopener">talk to a person on WhatsApp</a>.`;
    }

    function send(text) {
      if (!text.trim()) return;
      add(esc(text), "user");
      const t = add('<span class="ctc-typing" aria-label="Typing"><i></i><i></i><i></i></span>', "bot");
      setTimeout(() => { t.innerHTML = answer(text); log.scrollTop = log.scrollHeight; }, reduce ? 0 : 650);
    }

    let greeted = false;
    const open = (v) => {
      panel.classList.toggle("is-open", v);
      btn.parentElement.style.visibility = v ? "hidden" : "";
      if (v) {
        if (!greeted) { add("Welcome to Cabo Transportation Concierge customer help. Where are you staying? I'll quote your private transfer in seconds.", "bot"); greeted = true; }
        setTimeout(() => input.focus(), 300);
      } else btn.focus();
    };
    btn.addEventListener("click", () => open(true));
    $(".ctc-chat-close", panel).addEventListener("click", () => open(false));
    panel.addEventListener("keydown", (e) => { if (e.key === "Escape") open(false); });
    $("form", panel).addEventListener("submit", (e) => { e.preventDefault(); send(input.value); input.value = ""; });
    $$(".ctc-chips button", panel).forEach((b) => b.addEventListener("click", () => send(b.textContent)));
  }

  const start = () => { initBooking(); initMotion(); initAgent(); };
  if (window.CTC_DATA) start(); else addEventListener("load", start);
})();
