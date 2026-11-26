# Design Thinking & Audience Notes (`DESIGN.md`)

## 1. Audience, Viewing Context & Intent

- **Audience**: Ethiopian families and young adults in the diaspora, plus friends/relatives back home.
- **Where they watch**: Vertical feeds (`9:16`) on phones (TikTok, Reels, YouTube Shorts) and horizontal (`16:9`) on YouTube/laptops.
- **Core Intent**: Evoke quiet warmth, patience, and pride in everyday craftsmanship passed down across generations.
- **Template Story (`storyboard.json`)**: *The Brass Dial of Dessie* (9 shots, 68.0s story + 2.5s AI end card = 70.5s, Amharic narration with English subtitles). Customize `storyboard.json` with your personal family story before shooting live models.

## 2. Shot-by-Shot Justification

Every shot in `storyboard.json` carries an explicit `reason` field enforced by `schema/storyboard.schema.json`:
1. `shot_01` (*Dessie Hillside Dawn*, extreme wide): Establishes geographic setting before entering the shop.
2. `shot_02` (*Shop Shutters*, wide): Introduces Ato Tesfaye and the scale of the wooden workshop.
3. `shot_03` (*The Heirloom Radio*, insert): Focuses on the broken brass-dial radio motif.
4. `shot_04` (*Inspecting the Tubes*, medium): Shows posture and draws the viewer closer to the craft.
5. `shot_05` (*Hands and Solder*, close-up): Intimate detail of steady hands reconnecting a copper coil.
6. `shot_06` (*Memory on the Wall*, medium close-up): Links the physical repair to family across distance.
7. `shot_07` (*Turning the Dial*, extreme close-up): Builds quiet climax tension right before the dial glows.
8. `shot_08` (*The Warm Smile*, close-up): Delivers the emotional payoff when the broadcast returns.
9. `shot_09` (*Evening Workshop*, wide pull-out): Bookends the opening wide shot as the workshop glows at dusk.

---

## 3. User Test 1 — Radio Cut (Prototype)

*Run `python -m pipeline narration && python -m pipeline assemble --radio-cut`, then play `outputs/radio_cut/radio_cut_16x9.mp4` to at least 3 people from your intended audience and record their exact feedback and resulting `storyboard.json` changes below.*

| Tester (Relationship / Role) | Date | What Landed | What Confused or Dragged | Storyboard / Script Change Made |
|---|---|---|---|---|
| Tester 1 *(pending)* | | | | |
| Tester 2 *(pending)* | | | | |
| Tester 3 *(pending)* | | | | |

---

## 4. User Test 2 — Near-Final Cut

*Show `outputs/final/film_9x16.mp4` and `outputs/final/film_16x9.mp4` to at least 3 people from your audience (on a phone speaker and headphones) and record observations + edits below.*

| Tester (Relationship / Role) | Date | Pacing / Subtitles / Audio Balance Notes | Identity / Visual Notes | Final Edit Change Made |
|---|---|---|---|---|
| Tester 1 *(pending)* | | | | |
| Tester 2 *(pending)* | | | | |
| Tester 3 *(pending)* | | | | |
