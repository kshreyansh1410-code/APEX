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
  return `BATCH-01-${code}`;
}

async function submitToEndpoint(email) {
  if (!FORM_ENDPOINT) {
    const stored = JSON.parse(localStorage.getItem("apex_waitlist") || "[]");
    stored.push({ email, ts: Date.now() });
    localStorage.setItem("apex_waitlist", JSON.stringify(stored));
    return true;
  }

  const response = await fetch(FORM_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ email }),
  });
  return response.ok;
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
      form.hidden = true;
      successState.hidden = false;
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
