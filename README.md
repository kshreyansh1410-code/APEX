# APEX

A mobile-first landing page for **apex.**, a premium Gen-Z hair care brand. The page is a
zero-cost validation portal: it collects email sign-ups for the private "Batch №1"
pre-order waitlist. There is no cart and no payment flow anywhere on the page.

## Running locally

It's static — no build step. Serve the folder and open it:

```bash
python3 -m http.server 8000
# then visit http://localhost:8000
```

## Wiring up real email capture

`script.js` has a `FORM_ENDPOINT` constant at the top. Until it's set, submissions are
saved to `localStorage` on the visitor's own browser only, so the demo works but nothing
is actually collected.

To collect real sign-ups for free, create a form at a service like
[Formspree](https://formspree.io) or [Getform](https://getform.io), copy the endpoint
URL it gives you, and set:

```js
const FORM_ENDPOINT = "https://formspree.io/f/your-form-id";
```

The existing `fetch` call in `script.js` already POSTs `{ email }` as JSON to that URL.

