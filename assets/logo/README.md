# tomymind &mdash; logo & brand

The tomymind mark is a fresh **orange bookmark card** arriving in a
**deep navy library**. It's a direct nod to mymind's own visual signature:
the [iconic orange placeholder](https://mymind.com/artworks) that
appears the instant you save something, before the screenshot loads. For
`tomymind` (which exists to bring scattered bookmarks *to* mymind), it
made sense to picture that card mid-arrival.

## Files

| File | Use |
|---|---|
| [`tomymind.svg`](./tomymind.svg) | Primary horizontal lockup. Use on light / cream backgrounds. |
| [`tomymind-dark.svg`](./tomymind-dark.svg) | Inverse lockup. Use on navy / dark backgrounds. |
| [`tomymind-mark.svg`](./tomymind-mark.svg) | Square mark only. Use for favicons, app icons, avatars, social previews. |
| [`tomymind-wordmark.svg`](./tomymind-wordmark.svg) | Wordmark only. Use when the mark would be redundant (e.g. next to a hero illustration). |

Companion PNGs (rendered at 2&times; for retina) live next to each SVG
for contexts that don't render SVG.

## Palette

| Swatch | Name | Hex | Role |
|---|---|---|---|
| ![#FF4F1F](https://placehold.co/16x16/FF4F1F/FF4F1F.png) | Zima orange | `#FF4F1F` | Signature accent &mdash; the card, the brand spark. Never tint, never desaturate. |
| ![#0E1A2E](https://placehold.co/16x16/0E1A2E/0E1A2E.png) | Deep navy | `#0E1A2E` | Container, body text on light. |
| ![#FAF6F0](https://placehold.co/16x16/FAF6F0/FAF6F0.png) | Cream | `#FAF6F0` | Body text on dark, container on dark backgrounds. |

## Typography

Wordmark set in **Cormorant Garamond Medium (500)** with `-4` letter-spacing
at 140&nbsp;px. Fallback chain in the SVGs: `'Cormorant Garamond', 'EB
Garamond', 'Playfair Display', Georgia, 'Times New Roman', serif` &mdash;
which means the wordmark degrades gracefully to Georgia on systems that
don't fetch the Google Font.

If you embed the logo in HTML and want pixel-perfect rendering, drop this
in your `<head>`:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500&display=swap" rel="stylesheet">
```

## Embedding

### GitHub README (theme-aware)

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/logo/tomymind-dark.svg">
  <img src="assets/logo/tomymind.svg" alt="tomymind" width="420">
</picture>
```

### Plain HTML

```html
<img src="assets/logo/tomymind.svg" alt="tomymind" height="60">
```

### Favicon

```html
<link rel="icon" type="image/svg+xml" href="assets/logo/tomymind-mark.svg">
```

## Don'ts

- **Don't recolor the card.** Zima orange is the brand &mdash; swapping it
  to another color defeats the visual reference to mymind.
- **Don't add a stroke / outline / drop-shadow** to either shape. The mark
  is intentionally flat.
- **Don't squish the lockup.** When you scale, scale uniformly. The SVGs
  have a fixed `viewBox`, so `width="…"` alone is enough.
- **Don't put the light lockup on a dark background** (or vice versa).
  Use the matching variant.

## Credit

Palette and mood are inspired by the
[mymind artworks gallery](https://mymind.com/artworks). `tomymind` is a
personal project; mymind itself is a trademark of mymind GmbH and is
not affiliated with this repository.
