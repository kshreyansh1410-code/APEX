// Swap in a real form endpoint (e.g. a free Formspree/Getform form) to
// actually collect emails. Until then, signups are stored locally so the
// page can still be demoed end-to-end. See README for setup.
const FORM_ENDPOINT = "";

const form = document.getElementById("signupForm");
const emailInput = document.getElementById("email");
const fieldError = document.getElementById("fieldError");
const submitBtn = document.getElementById("submitBtn");
const successState = document.getElementById("successState");
const successEmail = document.getElementById("successEmail");
const successCode = document.getElementById("successCode");

function isValidEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

function makeWaitlistCode() {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  let code = "";
  for (let i = 0; i < 6; i++) {
    code += chars[Math.floor(Math.random() * chars.length)];
  }
  return `REVLUME-B1-${code}`;
}

async function submitToEndpoint(email) {
  if (!FORM_ENDPOINT) {
    const stored = JSON.parse(localStorage.getItem("revlume_waitlist") || "[]");
    stored.push({ email, ts: Date.now() });
    localStorage.setItem("revlume_waitlist", JSON.stringify(stored));
    return true;
  }

  const response = await fetch(FORM_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ email }),
  });
  return response.ok;
}

const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function revealSuccess() {
  if (prefersReducedMotion) {
    form.hidden = true;
    successState.hidden = false;
    return;
  }

  form.classList.add("is-leaving");
  window.setTimeout(() => {
    form.hidden = true;
    successState.hidden = false;
    successState.classList.add("success--enter");
    // Force layout so the browser registers the "enter" state before
    // it's removed, otherwise both changes collapse into one frame
    // and the 3D flip-in never renders.
    successState.offsetHeight;
    successState.classList.remove("success--enter");
  }, 250);
}

if (form) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = emailInput.value.trim();

    if (!isValidEmail(email)) {
      fieldError.hidden = false;
      emailInput.focus();
      return;
    }

    fieldError.hidden = true;
    submitBtn.disabled = true;
    submitBtn.textContent = "Joining…";

    try {
      const ok = await submitToEndpoint(email);
      if (!ok) throw new Error("submission failed");

      successEmail.textContent = email;
      successCode.textContent = `Waitlist ref — ${makeWaitlistCode()}`;
      revealSuccess();
    } catch (err) {
      fieldError.textContent = "Something went wrong — please try again.";
      fieldError.hidden = false;
      submitBtn.disabled = false;
      submitBtn.textContent = "Join the Batch #1 Private Waitlist";
    }
  });
}

// sticky mobile CTA, shown once the hero's own CTA scrolls out of view
const heroCta = document.querySelector(".hero .cta--primary");
const stickyCta = document.getElementById("stickyCta");
if ("IntersectionObserver" in window && heroCta && stickyCta) {
  const stickyObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        stickyCta.classList.toggle("is-visible", !entry.isIntersecting);
      });
    },
    { threshold: 0 }
  );
  stickyObserver.observe(heroCta);
}

// Once an entrance animation (brandmark, bottles) finishes, drop it so the
// plain tilt transform below can take over the element's `transform`
// property instead of the animation's held end frame.
document.querySelectorAll(".brandmark, .bottle").forEach((el) => {
  el.addEventListener("animationend", () => el.classList.add("tilt-settled"), { once: true });
});

// 3D pointer tilt — desktop/trackpad only. Touch devices keep the static
// (zero-rotation) resting transform already defined in CSS, so nothing
// here is required for the page to look correct on a phone.
const supportsHoverTilt =
  !prefersReducedMotion && window.matchMedia("(hover: hover) and (pointer: fine)").matches;

if (supportsHoverTilt) {
  document.querySelectorAll("[data-tilt-card]").forEach((card) => {
    const maxDeg = Number(card.dataset.tiltMax) || 8;

    card.addEventListener("pointermove", (event) => {
      const rect = card.getBoundingClientRect();
      const px = (event.clientX - rect.left) / rect.width - 0.5;
      const py = (event.clientY - rect.top) / rect.height - 0.5;
      card.style.setProperty("--tilt-ry", `${(px * maxDeg * 2).toFixed(2)}deg`);
      card.style.setProperty("--tilt-rx", `${(py * maxDeg * -2).toFixed(2)}deg`);
    });

    card.addEventListener("pointerleave", () => {
      card.style.setProperty("--tilt-rx", "0deg");
      card.style.setProperty("--tilt-ry", "0deg");
    });
  });
}
