---
name: wensity-landing-composer
description: Lay out a marketing site or landing page from Wensity UI blocks and components - a section order (navbar, hero, social proof, how it works, features, pricing, FAQ, CTA, footer) mapped to Wensity block categories with free fallbacks, a motion budget, performance and accessibility rules, copy kept in one typed file, and Pro license checks. Use when the user wants a landing page, product or portfolio site, pricing page or "make my site look like Wensity's demos" in React/Next.js.
---

# Wensity landing composer

Wensity has 87 Pro **blocks** (full sections, 14 categories), 115 **components** (38 free) and 57
free **primitives**, plus three Next.js templates (Fintech, Docs Site, Minimalistic Portfolio).
Blocks and templates need Pro (or the template bought on its own). Start with what the page must
say, then pick sections. Never start from the flashiest component.

## 1. Brief (ask if missing)

Audience, the single action you want visitors to take, three proof points (numbers, logos,
quotes the user actually has), pricing or not, and Free-only or Pro. Don't invent testimonials,
customer logos or metrics. Leave a marked placeholder instead.

## 2. Section order

| # | Section | Wensity block category (Pro) | Free fallback |
|---|---|---|---|
| 1 | Navbar | `navbars` | Navigation Menu + Sheet (mobile) primitives |
| 2 | Hero: promise + action | `hero-sections` | Text animation (e.g. text-blur-reveal) + Button; Background Studio still image |
| 3 | Social proof | `social-proof-sections` (metric bento) | Infinite Marquee of logos, Count Up for numbers |
| 4 | How it works | `how-it-works-sections` | Tabs or a three-step Card row |
| 5 | Features | `feature-sections`, `bento-grids` | Bento Grid Layout component, Card grid |
| 6 | Comparison (optional) | `comparison-sections` | Table primitive |
| 7 | Pricing (optional) | `pricing-sections` | Subscription Tier Card; Switch for monthly/annual |
| 8 | FAQ | `faq-sections` | Accordion primitive |
| 9 | Final CTA | `cta-sections` | Card + Button |
| 10 | Footer | `footers` | Separator + link columns |

Other categories: `contact-sections`, `login-pages`, `motion`. Find candidates with
`wensity_search` (`kind` block/component, `tier` free) and confirm the tier in the result before
proposing. Free/Pro labels on the website aren't always shown.

## 3. Motion budget

- **One showpiece per page** (a WebGL orb, liquid metal, black-hole hero…), above the fold or
  nowhere. Everything else gets subtle motion (fades, text reveals, hover states).
- Respect `prefers-reduced-motion`. Most Wensity components show a finished state; check each one
  you add, and test with the OS setting on.
- WebGL and canvas pieces: load them client-side after first paint (`next/dynamic` with
  `ssr: false`, or an intersection observer), give them a fixed size so the layout doesn't jump,
  and provide a static poster image. Export backgrounds from Background Studio as images (free)
  rather than shipping a shader when a still image does the job.

## 4. Build rules

- Copy lives in one typed file (`src/content.ts`), as Wensity's templates do; sections read
  from it.
- Theme comes from `wensity-brand-preset`. No hex colors in sections.
- Real elements: links are `<a>`, actions are `<button>`, one `<h1>`, ordered headings, alt text,
  visible focus rings, 4.5:1 text contrast, including on top of animated backgrounds.
- Plan and install through the `wensity-ui-scout` agent; install only after the user approves.
- Measure: Lighthouse (mobile) for LCP, CLS and total JavaScript. Vendor "100 score" claims assume
  optimized images and a fast network, so test it yourself.

## 5. License check (Pro)

Pro source covers unlimited personal, commercial and client work for **one developer per
license**, and may be modified, but **not redistributed** as a library, template, UI kit or public
repository. Before pushing, ask whether the repo is public. If it is, keep Pro components out
(free items are MIT) or make the repo private. Team use needs seats.
