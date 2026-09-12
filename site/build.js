// Builds the site from the mirrored All Ways pages: rebrand, recolor, local assets, Instagram info.
// Pages: original.html -> index.html, arrival-original.html -> arrival-guide.html
// Run: node build.js
const fs = require("fs");

const BRAND = "Cabo Transportation Concierge";
const PHONE_DISPLAY = "+52 (624) 000 0000"; // TODO: real WhatsApp number from the client
const PHONE_WA = "520000000000";
const EMAIL = "info@cabotransportationconcierge.com"; // TODO: confirm with client
const IG = "https://www.instagram.com/cabotransportation_concierge/";

function transform(h, { home }) {
  /* ---------- Scripts, fonts, styles ---------- */
  h = h.replace(/<script\b(?![^>]*application\/ld\+json)[^>]*>[\s\S]*?<\/script>/gi, "");
  h = h.replace(/<link[^>]+(modulepreload|typekit)[^>]*>/gi, "");
  h = h.replace(/<link rel="preload" as="style"[^>]*>/gi, "");
  h = h.replace(/<link[^>]+href="(?:https:\/\/www\.allwayscabotransportation\.com)?\/build\/assets\/[^"]+\.css"[^>]*>/gi, "");
  h = h.replace(
    "</head>",
    `<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Playfair+Display:ital,wght@0,500;0,600;0,700;1,600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="build/assets/app-aa22398b.css">
<link rel="stylesheet" href="build/assets/components.css">
<link rel="stylesheet" href="luxe.css">
<script src="data.js" defer></script>
<script src="luxe.js" defer></script>
</head>`
  );

  /* ---------- Local asset paths ---------- */
  h = h.replace(/https:\/\/www\.allwayscabotransportation\.com\/(images|videos)\//g, "$1/");
  h = h.replace(/(src|href|poster)="\/(images|videos)\//g, '$1="$2/');
  h = h.replace(/srcset="([^"]+)"/g, (m, v) => `srcset="${v.replace(/(^|,\s*)\/(images|videos)\//g, "$1$2/")}"`);
  // Internal pages that don't exist in this prototype keep the user on the page.
  h = h.replace(/href="(?:https:\/\/www\.allwayscabotransportation\.com)?\/(?!\/)([^"]*)"/g, (m, p) => {
    if (p === "") return 'href="index.html"';
    if (/^arrival-guide/.test(p)) return 'href="arrival-guide.html"';
    if (/^(booking|cabo-shuttle-prices)/.test(p)) return 'href="index.html#booking"';
    if (/^faq/.test(p)) return 'href="index.html#faq"';
    if (/^reviews/.test(p)) return 'href="index.html#testimonials"';
    if (/^contact/.test(p)) return 'href="#contact"';
    if (/^(images|videos|build)\//.test(p)) return m;
    return 'href="#"';
  });
  h = h.replace(/href="https:\/\/www\.allwayscabotransportation\.com"/g, 'href="index.html"');

  if (home) {
    /* Hero: Suburban instead of the Cadillac promo video */
    h = h.replace(/<img class="hero-promo-video__poster"[^>]*>/, `<img class="hero-promo-video__poster" src="hero-suburban.jpg" width="2000" height="1134" fetchpriority="high" decoding="async" alt="Black Chevrolet Suburban at sunset in Cabo San Lucas" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:center 62%;">`);
    h = h.replace(/<video\b[\s\S]*?<\/video>/g, "");
    // Generated promo video (video/generate.mjs + video/compose.mjs) plays over the photo once it exists.
    if (fs.existsSync("videos/hero-promo.mp4")) {
      h = h.replace(/(<img class="hero-promo-video__poster"[^>]*>)/, `$1<video class="hero-promo-video__el ctc-hero-video" autoplay muted loop playsinline preload="auto" poster="videos/hero-promo-poster.jpg" aria-hidden="true" tabindex="-1" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:center;"><source src="videos/hero-promo-light.webm" type="video/webm"><source src="videos/hero-promo-light.mp4" type="video/mp4"></video>`);
    }
    h = h.replace('class="relative z-10 bg-[#0b1e2d] text-center', 'id="booking" class="ctc-hero-copy relative z-10 bg-[#0b1e2d] text-center');

    /* Yacht promo slideshow (rendered empty on the server) */
    h = h.replace('<div class="phoenix-promo__slideshow"><!----></div>', '<div class="phoenix-promo__slideshow"><img src="yacht-arch.jpg" alt="Private yacht at The Arch in Cabo San Lucas" loading="lazy" width="1600" height="907" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover"></div>');
  } else {
    /* Arrival guide: video player (client-rendered on the original) + hero photo without the old branding */
    h = h.replace('<div class="aspect-video w-full relative"><!----></div>', '<div class="aspect-video w-full relative"><video class="absolute inset-0 w-full h-full object-cover" controls playsinline preload="metadata" poster="sprinter-interior.jpg"><source src="videos/video.mp4" type="video/mp4">Your browser does not play this video.</video></div>');
    h = h.replace(/(src|srcset)="images\/home\/cabo-airport-arrival\.webp"/g, '$1="hero-suburban.jpg"');
  }

  /* ---------- Photos that show the previous company's branding ---------- */
  const swapImg = (num, file) => {
    h = h.replace(new RegExp(`(src|srcset)="[^"]*reviews-all-ways-cabo-transportation${num}-[^"]*"`, "g"), (m, attr) => `${attr}="${file}"`);
  };
  swapImg(19, "sprinter-interior.jpg"); // wooden "ALL WAYS CHECK POINT" paddle
  swapImg(20, "yacht-arch.jpg"); // honeymoon sign with the old logo

  /* ---------- Logo ---------- */
  h = h.replace(/images\/svg\/logo-white\.svg/g, "images/svg/logo-ctc.svg");

  /* ---------- Remove the previous agency / sister brands ---------- */
  h = h.replace(/<section class="cabo-brands-network[\s\S]*?<\/section>/g, "");
  h = h.replace(/<a[^>]*marketingeleven[\s\S]*?<\/a>/gi, "");
  h = h.replace(/Custom Web Development, SEO &amp; Digital Marketing By/g, "");
  h = h.replace(/Select Photography By\s*(<[^>]+>\s*)*Carlos Plazola/g, "");

  /* ---------- Brand name ---------- */
  h = h
    .replace(/ALL WAYS CABO CHECKPOINT/g, "CABO TRANSPORTATION CONCIERGE")
    .replace(/All Ways Cabo Transportation/g, BRAND)
    .replace(/All ?Ways Cabo Boats/gi, `${BRAND} Yachts`)
    .replace(/All Ways Cabo/g, BRAND)
    .replace(/AllWays Hostess/g, `${BRAND} hostess`)
    .replace(/All ?Ways/g, BRAND)
    .replace(/allwayscaboboats\.com[^"]*/g, "#")
    .replace(new RegExp(`\\b([Aa])n ${BRAND}`, "g"), `$1 ${BRAND}`);

  /* ---------- Contact: Instagram says "Book by DM & WhatsApp", Cabo San Lucas ---------- */
  h = h
    .replace(/\+52\s?\(?624\)?\s?129\s?7911/g, PHONE_DISPLAY)
    .replace(/\(619\)\s?354\s?3205/g, PHONE_DISPLAY)
    .replace(/(wa\.me\/|tel:\+?)(52)?1?6241297911/g, `$1${PHONE_WA}`)
    .replace(/tel:\+?(52|1)?6193543205/g, `tel:+${PHONE_WA}`)
    .replace(/\+?(52|1)?\s?6241297911|\+?(52|1)?\s?6193543205/g, `+${PHONE_WA}`)
    .replace(/https:\/\/www\.allwayscabotransportation\.com/g, "https://www.cabotransportationconcierge.com")
    .replace(/info@allwayscabotransportation\.com/g, EMAIL)
    .replace(/"alternateName":\["Allways Cabo Transportation"\],?/g, "")
    .replace(/"sameAs":\[[^\]]*\]/g, `"sameAs":["${IG}"]`)
    .replace(/<a[^>]*href="\/cdn-cgi\/l\/email-protection[^"]*"[^>]*>[\s\S]*?<\/a>/g, `<a href="mailto:${EMAIL}">${EMAIL}</a>`)
    .replace(/<span class="__cf_email__"[^>]*>\[email&#160;protected\]<\/span>/g, EMAIL)
    .replace(/\[email&#160;protected\]/g, EMAIL)
    .replace(/Calle Los Pirules, lote 04, Fracc B,?/g, "Cabo San Lucas,")
    .replace(/Colonia Buenos Aires,? (San José del Cabo, BCS 23436|C\.P 23436)/g, "Baja California Sur")
    .replace(/Parcela 36,? lote K,? Local 4,? Plaza( Coronado)?,?/g, "Cabo San Lucas,")
    .replace(/Coronado\. Colonia El Tezal\./g, "Baja California Sur")
    .replace(/Colonia El Tezal, Cabo San Lucas, BCS 23454/g, "Baja California Sur");

  /* ---------- Colors: inline SVG / style attributes (Tailwind class names stay intact) ---------- */
  const HEX = { "007a96": "8C6D33", "FFC107": "D9B872", "ffc107": "D9B872", "0b1e2d": "07090D", "0a111a": "07090D", "123246": "0C0F14" };
  h = h.replace(/(fill|stroke|stop-color)="#([0-9a-fA-F]{6})"/g, (m, a, x) => (HEX[x] ? `${a}="#${HEX[x]}"` : m));
  h = h.replace(/style="([^"]*)"/g, (m, s) => `style="${s.replace(/#([0-9a-fA-F]{6})/g, (mm, x) => (HEX[x] ? "#" + HEX[x] : mm))}"`);

  if (home) {
    /* ---------- Instagram concierge strip, right after the hero ---------- */
    const icon = (d) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
    const services = [
      ["Private Transportation", "Suburbans and Sprinters", icon('<path d="M3 16v-4l2-5h14l2 5v4"/><path d="M3 16h18v2H3z"/><circle cx="7" cy="18" r="1.6"/><circle cx="17" cy="18" r="1.6"/><path d="M5 12h14"/>')],
      ["Yachts", "Private charters at The Arch", icon('<path d="M3 17c3 2 6 2 9 0s6-2 9 0"/><path d="M5 14h14l-2 3H7z"/><path d="M12 3v11M12 4l6 8h-6"/>')],
      ["Private Tours", "Your group, your pace", icon('<path d="M12 21s-7-6.2-7-11a7 7 0 0114 0c0 4.8-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/>')],
      ["Luxury Villas", "Pedregal, Palmilla, Diamante", icon('<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>')],
      ["Activities", "Desert, ocean and golf", icon('<circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/>')],
      ["Airport Arrivals", "Meet and greet at SJD", icon('<path d="M2 16l20-6-2-2-7 2-5-5-2 1 3 5-5 2-2-1-1 1 3 3z"/><path d="M3 21h18"/>')],
    ];
    const igStrip = `<section class="ctc-ig ctc-aurora" id="concierge">
  <div class="ctc-ig-inner">
    <div>
      <p class="ctc-ig-eyebrow">📍 Cabo San Lucas</p>
      <h2>Private transportation, yachts, tours, villas and activities in one call</h2>
      <p>${BRAND} plans the rest of your trip too. Book your ride, a yacht day, a private tour or a luxury villa directly by Instagram DM or WhatsApp.</p>
      <div class="ctc-ig-actions">
        <a class="ctc-ig-btn ctc-ig-btn--gold" href="https://wa.me/${PHONE_WA}" target="_blank" rel="noopener">Book by WhatsApp</a>
        <a class="ctc-ig-btn ctc-ig-btn--line" href="${IG}" target="_blank" rel="noopener">Send us a DM @cabotransportation_concierge</a>
      </div>
    </div>
    <div class="ctc-services">${services.map(([t, s, i]) => `<div class="ctc-service">${i}<strong>${t}</strong><span>${s}</span></div>`).join("")}</div>
  </div>
</section>`;
    const mainStart = h.indexOf("<main");
    const firstSection = h.indexOf("<section", mainStart);
    const secondSection = h.indexOf("<section", firstSection + 10);
    h = h.slice(0, secondSection) + igStrip + h.slice(secondSection);
  }

  /* ---------- Floating AI concierge + WhatsApp ---------- */
  h = h.replace(
    "</body>",
    `<div class="ctc-float">
  <button class="ai" type="button" data-ctc-ai aria-label="Open customer help chat"><span class="ai-dot" aria-hidden="true"></span><svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 13v-1a8 8 0 0116 0v1"/><rect x="2.5" y="13" width="4" height="6" rx="1.5"/><rect x="17.5" y="13" width="4" height="6" rx="1.5"/><path d="M19.5 19c0 1.7-1.6 2.5-4 2.5H13"/></svg><span class="ai-label">Customer Help</span></button>
</div>
<a class="ctc-wa" href="https://wa.me/${PHONE_WA}" target="_blank" rel="noopener" aria-label="Chat with us on WhatsApp"><svg width="32" height="32" viewBox="0 0 24 24" aria-hidden="true"><path fill="#FFFFFF" d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg></a>
</body>`
  );
  return h;
}

const pages = [
  ["original.html", "index.html", { home: true }],
  ["arrival-original.html", "arrival-guide.html", { home: false }],
];
for (const [src, out, opts] of pages) {
  const h = transform(fs.readFileSync(src, "utf8"), opts);
  fs.writeFileSync(out, h);
  console.log(out, (h.length / 1024).toFixed(0) + "KB",
    "| leftover 'All Ways':", (h.match(/All ?Ways/gi) || []).length,
    "| leftover old phones:", (h.match(/129 ?7911|354 ?3205/g) || []).length);
}

/* ---------- Recolor the compiled Tailwind + component CSS (values only, selectors untouched) ---------- */
const RGB = {
  "0 122 150": "140 109 51", "0 108 114": "140 109 51",
  "18 50 70": "12 15 20", "33 84 101": "28 32 40",
  "255 193 7": "217 184 114", "234 179 8": "198 161 91", "230 173 6": "198 161 91",
  "10 17 26": "7 9 13", "11 30 45": "7 9 13",
  "0 95 120": "111 86 39", "0 96 128": "111 86 39", "0 106 130": "111 86 39",
};
const CSSHEX = { "007a96": "#8C6D33", "ffc107": "#D9B872", "123246": "#0C0F14", "005f78": "#6F5627", "006080": "#6F5627", "006a82": "#6F5627", "e6ad06": "#C6A15B", "eab308": "#C6A15B", "0a111a": "#07090D", "0b1e2d": "#07090D" };
function recolor(src, out) {
  let css = fs.readFileSync(src, "utf8");
  css = css.replace(/rgba?\((\d+)[ ,]+(\d+)[ ,]+(\d+)/g, (m, r, g, b) => {
    const k = `${r} ${g} ${b}`;
    return RGB[k] ? m.replace(/\d+[ ,]+\d+[ ,]+\d+/, m.includes(",") ? RGB[k].replace(/ /g, ",") : RGB[k]) : m;
  });
  css = css.replace(/(?<!\\)#([0-9a-fA-F]{6})\b/g, (m, x) => CSSHEX[x.toLowerCase()] || m);
  css = css.replace(/sofia-pro/g, '"Outfit"').replace(/freight-display-pro/g, '"Playfair Display"');
  css = css.replace(/url\((['"]?)\/(images|fonts|build)\//g, "url($1../../$2/");
  fs.writeFileSync(out, css);
}
recolor("build/assets/app-original.css.bak", "build/assets/app-aa22398b.css");
recolor("build/assets/components-original.css", "build/assets/components.css");
