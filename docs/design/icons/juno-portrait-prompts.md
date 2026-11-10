# Juno portrait: 10 styles to generate

Michael (2026-11-08): the hand-drawn faces were too cartoony. He wants something epic, ideally a real-looking person
he is talking to, inspired by the goddess Juno but not a costume copy. Blue leaning. "Queen of the home" was the best
of the first round.

Juno can't render photoreal images from code, so these are prompts for an image model (ChatGPT image generation,
Google Gemini, Midjourney, Ideogram or Adobe Firefly all work). Paste one prompt, keep the ones you like, and Juno sets
the winner as the Slack icon.

## Same woman in every style
So the ten are comparable, every prompt describes the same person:
> a woman in her mid thirties, warm olive skin, dark brown hair, strong brows, calm intelligent dark eyes, a slight
> knowing half smile, regal posture

Her signs, used lightly: a gold diadem, peacock feathers, a pale veil, the new moon, deep blue and gold.

## For Slack
Add this line to every prompt: `square 1:1, head and shoulders, face centered and filling the middle third, simple
background, no text, no watermark, no logo`. Slack shows the icon at 36 px in messages and 20 px in the sidebar, so a
clear face and strong contrast beat fine detail. Export at 1024 x 1024 or larger.

## The ten

### 1. Studio portrait (photoreal)
A real person in a portrait session. The closest to "talking to someone".
> Photorealistic studio portrait of [the woman], wearing a draped deep navy silk stola with a thin gold diadem set with
> one small peacock-blue stone, small gold earrings. Soft Rembrandt lighting, 85mm lens, shallow depth of field, dark
> slate blue backdrop, natural skin texture, looking straight into the camera.

### 2. Modern chief of staff (photoreal)
Inspired by the goddess, dressed for today. Someone you'd hire.
> Photorealistic editorial portrait of [the woman] as a confident executive: tailored navy blazer, cream silk blouse,
> a tiny gold laurel pin, hair in a low sleek bun, subtle peacock-feather earrings. Soft window light at dusk, blurred
> warm office behind her, friendly direct gaze, magazine cover quality.

### 3. Epic film still (cinematic)
An actress playing Juno in a big-budget epic.
> Cinematic film still of [the woman] as the Roman queen of the gods on a marble palace terrace at golden hour, white
> and gold gown, cobalt cloak, gold diadem, a peacock on the balustrade behind her out of focus. Anamorphic lens, rim
> light on her hair, volumetric haze, color graded teal and gold, photoreal.

### 4. Old master oil painting
Like a museum piece: classical, rich, timeless.
> Neoclassical oil painting of [the woman] enthroned, head and shoulders, ivory gown with a deep blue mantle, gold
> diadem, peacock feather fan at her shoulder, warm candlelit palace interior. Academic realism, visible brushwork,
> varnished glow, 19th century salon painting.

### 5. Living marble statue
Stone coming to life: epic and a little uncanny.
> Hyperreal sculpture of [the woman] carved in white marble with veins of gold, the stone cracking open at the
> shoulders to reveal glowing gold beneath, marble veil and diadem, eyes lifelike and warm. Dramatic museum spotlight,
> deep navy background, photoreal.

### 6. Fantasy game splash art
Like a hero card in a fantasy game: bold, glowing, heroic.
> Fantasy game splash art of [the woman] as a goddess of protection, ornate gold and sapphire armor over a white gown,
> peacock feathers spread behind her like a halo, holding a golden scepter, magical blue light swirling. Dramatic rim
> light, painterly digital art, highly detailed.

### 7. Anime key visual
Clean anime look, like a key visual for a series.
> Anime key visual of [the woman] as a celestial queen, long dark blue hair with gold ornaments and peacock-feather
> ribbons, white and gold dress, crescent moon and stars behind her, soft glow. Cel shading, crisp line art, vivid
> blue and gold palette.

### 8. Art Nouveau poster
Flowing hair, ornamental frame, poster art from around 1900.
> Art Nouveau poster of [the woman] in profile turning toward the viewer, flowing hair framed by a circular halo of
> peacock feathers, gold diadem, ornamental border of lilies, flat muted blues, teal and gold. Decorative line work,
> lithograph texture.

### 9. Celestial night goddess
Juno ruled the new moon. On duty while you sleep.
> Ethereal portrait of [the woman] as a night goddess, skin lit softly by moonlight, a sheer pale blue veil scattered
> with tiny stars, a thin crescent moon above her diadem, deep navy sky with faint nebula. Dreamy, luminous,
> photoreal with a soft glow.

### 10. 3D animated feature character
Warm and expressive, like the lead of an animated feature film. Friendly without being childish.
> Stylized 3D animated feature film character of [the woman] as a wise, warm queen, expressive eyes, gold diadem,
> navy and ivory robes, a small peacock at her shoulder. Soft cinematic lighting, subsurface skin, detailed hair,
> high-end 3D render.

## Notes
- Styles 1 to 3 are the "real person" end. Start there if that's the goal.
- Keep away from copying any one artist or game. These prompts name styles, not people.
- Later: an image and video agent could run these prompts itself (a `new-subagent` case; it needs an image model API
  and a key in 1Password).

## Chosen (2026-11-08)
Michael picked **1. Studio portrait**. Generated in ChatGPT, saved as `juno-icon.png` (1008 x 1008), and set as the
Juno app icon in Slack (Basic Information > Display Information) with background color #1F3B73.
