# Design: Llack

The locked system. Every build of Llack reads this first. Change it on purpose; the
file is the rule.

## System

- Genre: modern-minimal
- Shape: app screen (three-pane shell, thread pane on the right)
- Theme: Dose (warm paper, one pharmacy green, moulded plastic, DM Mono labels)
- Axes: light / grotesk-sans / chromatic-green · posture: restrained
- Signature: the message label — a mono timestamp set like a pharmacy label, beside a
  sans body, on a paper canvas

## Tokens

`desktop/src/styles/tokens.css` is the source of truth. Every colour, font, size and
duration in the app resolves from that one `:root` block; nothing literal appears
anywhere else in the stylesheet.

```css
:root {
  --color-paper: oklch(97.4% 0.008 88);   /* warm paper */
  --color-ink: oklch(21% 0.025 170);      /* green-black ink */
  --color-ink-2: oklch(31% 0.02 170);
  --color-muted: oklch(45% 0.024 165);    /* 7.1:1 on the canvas */
  --color-rule: oklch(87.5% 0.02 140);
  --color-accent: oklch(47% 0.13 160);    /* the one signal */
  --color-accent-lift: oklch(52% 0.12 158); /* the lit top of a green key */
  --color-accent-deep: oklch(38% 0.105 162);
  --color-accent-soft: oklch(91% 0.055 160);
  --color-accent-ink: oklch(99% 0.006 160);
  --color-focus: oklch(45% 0.14 160);
  --font-display: "Schibsted Grotesk", "Pretendard Variable", ui-sans-serif, sans-serif;
  --font-body: "Instrument Sans", "Pretendard Variable", ui-sans-serif, sans-serif;
  --font-outlier: "DM Mono", ui-monospace, monospace;
  --radius-input: 10px; --radius-field: 12px; --radius-card: 14px; --radius-panel: 16px; --radius-pill: 999px;
  --control-h: 34px; --rail-w: 264px; --thread-w: 400px; --header-h: 60px;
  --text-measure: 920px; /* where a line of message text ends */
  --agenda-measure: 720px; /* a day of events is a block, not a table row */
  --text-inset: 68px;      /* the conversation's frame: where the text starts, and where it ends */
  --composer-inset: 56px; /* the composer's card edge; its text lands on the message text */
  --bubble-mine: oklch(42% 0.115 161); /* your own message: the signal, as a surface */
  --bubble-mine-ink: oklch(98.5% 0.008 160);
  --edge-field: oklch(58% 0.022 165); /* a field edge clears 3:1, and stays light */
}
```

## Material

Surfaces climb one ladder and never skip a rung: `--surface-frame` → `--surface-rail`
→ `--surface-canvas` → `--surface-raise`, with `--surface-well` for inputs,
`--surface-groove` for a field cut into the rail, and `--surface-ink` for the ink
band.

A rung is told apart from the next by **elevation**, not by a hairline alone:

- A **raised** surface — composer, menus, dialogs, cards — wears one soft
  shadow (`--shadow-e1` … `--shadow-e3`). A floating surface carries a shadow
  **or** a hairline, never both: an edge and an elevation stacked on each other
  read as two edges.
- A **plastic** surface — the primary key, your own bubble, the brand tile —
  wears `--sheen` on its top edge and `--rim` on its bottom. Light falls on it.
- A **recessed** surface — inputs, the search groove — wears `--recess`, so light
  leaves its top edge.
- A **cut** surface — a field, a well — is cut *into* the panel it sits on: the
  edge of the cut is drawn inside the shape (`inset`), never laid around it, so
  the field reads as carved rather than laid on top. The cut is warm: a cold
  grey line around a cream field reads as a borrowed form.
- The canvas and the rail carry a fine **paper tooth** (`--tooth`). The paper is
  a material, not a flat fill.


## Layout

- The conversation **fills its pane**. The rows, the hover wash, the date rules,
  the header and the composer all reach the pane's edge, so the chat occupies
  the window instead of sitting in a ribbon with a dead band beside it.
- The column is **left-anchored**. A centred column re-centres every time the
  thread pane opens and the page shifts under the reader.
- **Your own message is the one exception**: it travels in a bubble against the
  right of the pane, so the conversation reads as two columns — theirs on the
  paper at the left, yours in the signal green at the right. The bubble is the
  only surface in the app that wears the signal colour (`--bubble-mine`), and
  its ink, its dim timestamp and the link colour inside it are one set
  (`--bubble-mine-ink`, `--bubble-mine-dim`, `--bubble-mine-link`). Your name is
  not repeated over your own words; the timestamp rides inside the bubble at its
  bottom-right. A mention inside the bubble inverts. The bubble stops growing at
  560px and wraps from there.
- **The conversation has one frame, and it is symmetric.** The left line is
  `--text-inset` — the row's padding, the avatar gutter and the gap, so the
  message text starts there. The right line is the same distance: their text,
  your bubble, the composer's text and its send key all stop on it. A
  conversation with one tight margin and one loose one reads unfinished; the
  row's wash and the date rules still reach the pane's edges, so the spread
  itself is unbroken.
- A line of message text ends where a line should end (`--text-measure`), but
  the row around it keeps going: a wide window reads as one spread
  conversation, not a column with a margin beside it.
- Everything that starts a block of text starts on the same line: the message
  text, the thread's reply count and the composer all sit on `--text-inset`, so
  nothing is left stranded in the avatar gutter.
- The **thread pane is 400px** — too narrow for an avatar column of its own. There
  the avatar sits beside the author name instead, and the pane's text, its reply
  count and its composer land on one line near the pane's edge. The pane fills
  its width; nothing is stranded in a corner. It is a sheet over the
  conversation: it carries a shadow of its own.
- The channel header bar spans the pane and its actions sit at the pane's edge;
  the channel name sits above the messages it names. Its tools sit in a groove
  cut into the bar.
- A message's **tools** — the emoji, reply and more buttons — belong to that
  message, so they stand against it rather than at the far edge of the row:
  just past the last word for someone else's message, just before the bubble
  for your own. Where the words end is measured, not guessed, so the tools
  follow the message whatever its length. Only when the pane is too narrow
  to hold them there do they float above the row.
- The composer's text column is the message text column, not the row's edge, and
  the composer ends exactly where the text column ends. The card is inset by the
  same distance on both sides, and what it holds lands on the conversation's
  frame — the text on the left line, the send key on the right one. A hairline
  rules the compose band across the whole pane, so the window is framed at the
  foot the way the header frames it at the top.
- Below 52rem the rail becomes an overlay behind the header's menu button; below
  60rem the thread pane overlays the conversation instead of taking a column.
- **Two panes, only when the window is wide.** From 72rem the conversation stays
  on the left and the board (calendar, work) opens beside it on the right; the
  board's own header moves it between that side pane and the whole main pane.
  Below 72rem there is room for one surface only, so the board takes the
  conversation's place instead of sitting beside it.
- **The rail's 일정 and 프로젝트 are switches.** They put the board beside the
  conversation, and pressed again while the screen is split they take the
  split away — the conversation fills the main pane again. From a split, the
  rail never moves the view to a full-width tab.
- **Whether the screen is split at all is this device's own.** The width of the
  window is the app's answer; the reader's setting is the other half, and it
  lives in 외관. With the split turned off, the board always takes the
  conversation's place, whatever the window is.
- **One selection at a time.** The rail paints the surface that was picked last
  with the selected wash — never two at once. A room that stays open beside the
  board keeps the app's own marks without the wash: its glyph wears the signal
  colour and its name is written in full ink, so it is still there without
  pretending to be the selection.
- **The rail's foot holds two things.** The profile, which is the last thing in
  the rail, and the settings gear beside it — the settings are one click away,
  without a menu. The profile keeps its own menu, and the gear opens the
  settings sheet where it stands.
- **The rail can be folded to a strip.** The fold is the reader's own — the key
  in the rail, or ⌘B — and it stays the next time the app opens. Folded, the
  rail is a strip of marks: the workspace, the switches, the rooms as their
  glyphs, the people as their faces, and a dot on the mark of a room that has
  something unread. The conversation takes the room the rail gave up.
- **The folded rail comes back over the conversation, never beside it.** The
  pointer on the strip (or the keyboard inside it) opens the rail *over* the
  pane, and leaving it folds the rail away again. A pane that moves under the
  reader is a pane that was never asked for.
- **The conversation may take the whole window.** The board's own header moves
  it between the side pane and the whole main pane; the conversation's header
  does the same. And the room that is already open, pressed again while the
  board sits beside it, gives the conversation the whole window — the board
  comes back through its own switch in the rail.
- **The screen can be cleared.** A key in the channel header's tools groove
  empties the workspace: the rail stays, the pane shows an empty state, and
  nothing is selected at all — no room, no board, no thread. Picking a room in
  the rail brings the conversation back. The empty state is the app's own
  empty state: a mark, a title and a sentence, never a blank page.
- **A room window is one conversation.** A room opened on its own has no rail:
  the header, the messages and the composer, and nothing else. The window's
  title is the room's name.

## Type

- Display (channel names, dialog titles, wordmark): Schibsted Grotesk 700, -0.03em.
- Body (everything else): Instrument Sans 400 / 500 / 600.
- Outlier (timestamps, counts, dates): DM Mono 400 / 500, one role only.
- Korean falls through to Pretendard Variable, bundled in `src/assets`.
- Message body 15px / 1.6. Labels 13px. Timestamps 11px, mono.
- Numbers that can change in place — counts, times, durations — are tabular.

## Controls

- Primary: green plastic, 10px radius, 34px high, lit on top and rimmed below,
  sinks 1px on press. **The key keeps its green under the pointer** — the
  hover lifts it (a little more light on the top stop, a deeper cast), and
  never repaints it with a surface its label cannot stand on.
- Secondary: outline on `--surface-raise`, same radius and height.
- Icon buttons: 30px square, no chrome until hover.
- A field is a **well**: cut into the surface it sits on, 40px high, 12px
  radius, the light staying at its top edge and its foot deeper. The focus
  ring is the accent — the cut's edge lights up and a soft halo answers it.
- **The mark in a box is ours too.** The platform's own checkbox paints with
  the operating system, and a grey plate inside a cream panel reads as
  something borrowed. Ours is a small recessed square that fills with the
  signal and carries a cut tick.
- **A choice between several ways is a dropdown field**: a well like any other
  field, and the list that comes out of it is a raised surface — the chosen row
  wears the signal colour, the way the selected day wears it on the calendar.
  The list is ours: the platform's `<select>` paints its menu with the
  operating system, so it can never wear this app's material. A row may lead
  with a mark — a face, a hash — so the choice says what it is before it is
  read. The arrows walk the list, Enter takes the row under the marker, and
  Escape gives the field its focus back and leaves the dialog behind it open.
  The field that picks **people** answers the same way — the same arrows, the
  same Enter, the same Escape — so the hand learns it once.
- Every control: default, hover, focus-visible, active, disabled, loading, error, success.
- A **disabled control is inert**: it neither lifts nor answers the pointer, and
  its label stays readable on the surface it actually has — a dimmed plate and
  muted ink, never a faded fill under a faded label.
- **The scrollbar belongs to the browser, not to us.** This is a desktop
  surface, scrolled with a wheel or a trackpad, so the bar never appears —
  the scroll itself is untouched. Only the bar is gone.

## Dialogs

A dialog is a **panel that hangs over the page**. It is not a rectangle with a
border.

- The page behind it is **pushed back, not hidden**: blurred, dimmed, and
  darkened at the edges. The panel is the one lit thing in the room.
- The panel is **centred** and carries a layered shadow — a contact shadow, a
  body shadow and a long cast — with a lit top edge. A panel with one hairline
  around it reads as a box drawn on the page.
- It is built in three bands: the **head** (the subject, with the key that
  closes it), the **body** (the content, and the only band that scrolls), and
  the **foot** (a shelf a step below the panel, where the actions stand at the
  edge of the sheet).
- Every dialog in the app is the same shell, so a form is recognisable before
  it is read: a new channel, an event, a card and an invite all arrive as the
  same object.

## Forms

A form is a **sheet of rows**. The name of the thing on the left, the thing you
fill in on the right, and a hairline between the rows. One row is one line, so
the whole form is read at a glance instead of scrolled through. The row is the
same shape the settings sheet uses — a name, and the control that changes it.

- **The title is not a row.** It is the subject of the form: the name of the
  thing written small and quiet above it, the thing itself written large in
  the display face, and a rule under it that reads like the first line of a
  note. The eye lands in one place.
- **A label sits beside its control, never above it.** A wall of labels stacked
  over their fields is the thing a form is trying not to be.
- **The rare fields are folded, not gone.** A **더 보기** row says what is
  inside it — "장소 · 설명 · 연결할 방" — so the reader knows the form can do
  more without opening it to find out. Nothing is removed from the product; it
  is only put away until it is wanted.
- **The platform's own date and time fields are never used.** They paint with
  the operating system, so they can never wear this app's material. A **day** is
  a well that opens the month's grid under itself — the same grid the schedule
  shows, so a day looks the same wherever it is picked. An **hour** is a well
  that opens a list of times, like every other choice.
- **The day is picked once.** A meeting names its day and its hours; it does not
  name its end day. When the end falls after the start, the row says so.
- **The keyboard is the control**, and it answers the way the dropdown answers:
  the field keeps the focus, the arrows walk a marker through the days, Enter
  takes the day under it, Escape closes the month and leaves the dialog open.

## Picking people

- A field that holds people is a **well that opens a list under itself** — not
  a menu that floats over the dialog, and not a list that is always there. The
  list opens below the field; when the window has no room below, it opens
  above.
- The list is **drawn over the page**, the way the menu of a plain dropdown is
  drawn: a dialog's overflow must never cut a roster of people in half. It
  measures the field, places itself under it, and follows it while the page
  scrolls.
- **The list opens with the search already focused.** A company has hundreds
  of people, and typing is the way in — so the reader may type the moment
  the list is open. Typing on the closed field opens the list and starts the
  search, the way the palette does.
- The search matches the **name, the email and the title, anywhere in the
  string**: "민수" finds "김민수", "minsu" finds "minsu@hanbit.co.kr".
- **The keyboard is the control.** The arrows walk a marker through the rows,
  Enter (and Space) take the row under the marker, Home and End jump to the
  first and the last row, the marked row scrolls into sight, and Escape closes
  the list and gives the field its focus back — the dialog behind it stays
  open. It is the same contract the plain dropdown answers with, so the hand
  learns it once.
- **The list is written for a company, not for a team of ten.** The people
  already chosen stand at the **top**, under a quiet label that counts them
  (**선택됨 N명**); the rest follow under **전체 N명**; the search says how
  many it found. The marker follows the filtered list, and it follows the
  person who has just been chosen.
- **The people already chosen stay in the list**, and each one carries a
  **tip** — a small green label with a tail that points back at the person.
  You can read who is in the room while you are still choosing it.
- The closed field holds the **faces** of the chosen people and their count in
  DM Mono, so the state is legible without opening the list.
- **Nothing found is a state of its own**: the list says that nobody was
  found, names the term that was searched for, and offers the way out — the
  search to clear.

## Motion

- Character: calm. `--dur-micro` 120ms for press and colour, `--dur-short` 200ms for
  hover and menus, `--dur-long` 320ms for dialogs and the thread sheet. Transform
  and opacity only.
- One authored moment: the thread sheet slides in as it opens. Nothing else
  moves on its own.
- Under `prefers-reduced-motion: reduce` everything ends at once.

## Dark mode

A derived night, not an inversion: the same green at `oklch(70% 0.12 158)` on an
`18.5%` canvas, a rail that sits a clear step below it, the same radius scale,
the same rules. `--color-focus` stays brighter there — a focus ring must pop on
a dark ground.

## The keyboard

The hand stays on the keyboard for the things it does all day.

- **⌘K** opens the palette — every room, every person, every project and every
  action in one list. The rooms you were in lately come first while the box is
  empty; a word in the box puts them away.
- **⌘B** folds the rail.
- **Alt+↑/↓** walks the rooms in the rail's order; **Alt+Shift+↑/↓** walks the
  rooms that have something unread. The walk stops at the ends — it never wraps
  around. The keys keep out of the way while a word is being written, and
  while a sheet is open.
- **A half-written line belongs to its room.** It stays when the room changes,
  when the composer goes away, and when the window is closed with the sentence
  still in it. A thread's answer is its own answer and never shares the room's
  line.

## Replies

There are two ways to answer a message, and one answer at a time.

- **The thread** is the reply that lives on the right. It never covers the
  channel.
- **The answer in the room** is the reply that shows where it was written: it
  sits in the channel, quoting the message it answers, and it joins that
  message's thread as well. So the thread holds every reply, and the room
  shows the ones written there.
- Either way the answered message's **reply count** counts them all, and the
  thread opens on them.
- Replies are **one level deep**. An answer to an answer joins the thread of
  the message that answer answered.
- The quote above an answer is one line: who was answered, and what they said,
  truncated. It is a **reference, not a second message** — clicking it walks
  back to the message it names and calls it out for a moment.
- The answer being written shows in the composer, above the input, naming the
  message it answers, and can be dismissed.
- A reply you accept wears the signal; a reply you decline does not.

## Presence

- A person wears one state, and it is a **live state chip on an avatar** — the
  same chip in every place: the rail, the member list, the message header.
- The states are the ones a team already reads at a glance: **온라인** (a green
  dot), **바쁨** (a red dot), **방해 금지** (a red dot with a bar through it),
  **잠시 자리 비움** (a pale amber ring), **곧 돌아오겠습니다** (a solid amber
  dot), and **오프라인** (a grey dot the server gives, never the person).
- The picker lives in the profile menu, beside the name: **상태 변경 ›** opens a
  second menu beside it, with the current state ticked. The submenu opens on
  hover and on click, and it closes with the menu it belongs to.
- A state the person chose is theirs until they choose another one — a socket
  opening does not turn "busy" into "online".

## Avatar colour

- A person's avatar colour is **theirs to choose**, in the profile settings.
- The palette is a fixed set of deep colours — the same seven the app has
  always handed out — so an avatar is recognisable at a glance. A free colour
  picker sits beside them for anyone who wants one of their own.
- Whatever is chosen is **darkened until paper-white initials on it are
  readable** (5:1). The hue is kept; only the lightness moves. A colour is
  never allowed to make a face unreadable. The initials are paper white in
  both themes, and the darkening is applied when the avatar is drawn — so a
  colour stored long ago is corrected too, not only one just chosen.
- The chosen colour is shown next to the swatches as a value, and the avatar
  beside them previews it live.
- A changed profile reaches the team at once: the roster updates without a
  reload.

## Settings

The app's own settings live in one place — a wide sheet with the sections
down the left and the section's content on the right.

- **Four sections, always the same four:** 알림 · 외관 · 계정 및 조직 ·
  파일 및 링크. The section in force is a surface in the signal colour, the
  way the selected day is on the calendar.
- **A row is a name, a sentence, and the control.** The sentence says what
  the control does — never that it exists.
- **A boolean is a moulded toggle**: a groove cut into the panel with a
  raised knob, filled with the signal when it is on. A choice between two
  or three ways is a segmented control in a well. Nothing else.
- **Settings split by owner.** The account's own — name, title, face, role —
  belong to the server and are edited here. The device's own — notifications,
  screen, files — stay on this machine. A setting that belongs to neither is
  not a setting.
- **The layout is a device setting too.** 외관 holds the screen mode, the
  clock, and whether the main pane is split at all — a reader who wants one
  surface at a time says so once, here.
- **Nothing is claimed that does not happen.** Every switch here changes
  something the app does: the notification preview really does change the
  notification, the screen mode really does follow the OS, the folder really
  does receive the file.

## Schedule

The calendar is a **picking** surface, not a reading one — so it is quieter
than the conversation.

- The month is a navigator: seven columns and a number. A day that has
  something on it says so with a **dot**, not a count — the count belongs to
  the day list, where the events are.
- **The dot says whose it is.** The signal green is a day you are in; quiet
  ink is a day the team has something on and you do not — the same division
  the day list and the **내 앞으로** card already make. A legend under the
  month says so with the same marks, and the selected day keeps the
  distinction too: full ink for yours, half for the team's.
- Today is marked by weight; the selected day by a surface. Neither uses a
  second hue.
- A day outside the month is present but dimmed — it is still a place.
- The day list reads left to right like a message: a mono time, then the
  title, then the place, then the people, then the faces. The time is in DM
  Mono because it is a label, not prose.
- On a wide window the days ahead stand beside the day in a card, so the
  width is used rather than left blank. **That card is yours**: it holds the
  events you are in — the team's day list stays the team's. Its heading says
  so, and an empty card says plainly that nothing of yours is coming up.
- An event you created wears no special colour. Ownership is carried by the
  roster and the answer, not by a badge.

## The board

The project board is the same shape as the calendar: a **picking** list on the
left, a **reading** surface on the right. The rules are the calendar's rules.

- The project list is a well cut into the app, like the month. The filter in
  force — 전체 / 내 프로젝트 — is a surface in the signal colour, the way the
  selected day is.
- A project is a name, a line about what it is for, and the faces of the
  people on it. Nothing else.
- **A project says three things about itself**, in one line under its name:
  how far it has come (a meter and its percentage), how much is left, and
  the period it runs in. A newcomer reads that line before the cards — a
  project is a piece of work with a shape, not a column of cards.
- The facts are separated by a hairline, not a middot: a middot left at the
  start of a wrapped line says nothing.
- **Two kinds of thing live in a project, and they never share a row.** 할 일
  (the cards) and 마일스톤 (dated goals) are picked by a **segmented control
  in a well** — a switch between two surfaces, each with its own count. The
  로드맵 filter then narrows the cards *inside* the 할 일 view: it filters
  one surface, it is not a peer of it.
- The lane filter is a **named** row — the word 로드맵 stands beside it —
  because a row of pills with no name is a row of tabs, and tabs at the same
  level are what made this surface unreadable.
- **The board and the lanes are told apart by a rule.** The first chip is
  모든 카드 — the whole board — and a vertical rule separates it from the
  roadmaps that follow. A chip named "전체" sitting among lane names reads
  like a lane called "전체"; "모든 카드" with a rule beside it cannot.
- **A project with no roadmaps shows no filter row at all.** There is
  nothing to narrow, so the board says so by being the board.
- The board is **four columns**, always the same four: 요청, 할 일, 진행 중,
  완료. A column is a well; a card is a raised surface on top of it. The
  column header carries a count in DM Mono — never a dot, never a colour.
- **A narrow pane holds two columns of cards, not four.** In the side pane
  the board folds to 2×2, so every column stays readable and the
  conversation keeps the other half of the window.
- **A deadline is said in words.** "3일 남음", "오늘 마감이", "2일 지남" — the
  badge is a label, not a colour. Late is the only tone that changes hue, and
  it still says how late.
- The assignee's face sits on the card, where a person's face always sits.
- Your own work is a separate, small list: **내 할일**. It holds the tasks
  that are yours and not finished, across every project — the same job
  **내 앞으로** does on the calendar.
- A card carries its own conversation: the number of opinions on it is a
  count in DM Mono, and the opinions themselves open beside the card.
- Moving a card is the reader's hand, not a dialog. The column lights up
  while a card is held over it, and a card can also be moved from a menu —
  the board is not a mouse-only surface.
- A room that belongs to a project says so in its header: the project's name
  sits in the same groove as the search and pin tools. The board and the
  conversation are one click apart.

## The project chart

The chart is a **reading** surface: the board's work on a time axis. It opens
as a modal from the project's own **period**, in the header — the chart is
that period drawn out, so the period is the way in. There is no second
entrance: an icon beside the project's name would say the same thing twice,
in a smaller voice.

- **The months are the ruler.** The chart spans only the months the project
  actually occupies — the first month a milestone or a deadline falls in,
  through the last. A month is as long as it really is; February is shorter
  and the chart says so. The year is named where it changes.
- **A milestone is a bar of its own colour.** The bar spans the period, and
  the part of it that is done is filled. The colour is the company's, chosen
  in the milestone dialog; it rides on a custom property, never on a literal.
- **The time axis is one trough.** Every mark of every row is drawn in the
  same recessed channel, so the plot reads as one instrument — not a bar
  chart with stray hairlines under it. The month rules run through the
  channel and the marks stand above it.
- **One mark language, and weight says what a mark is.** A **bar** is a
  period of work (a milestone). A **post** is a meeting. A **dot** is a
  card's 마감일. A **rule** over a soft band is today. The deadline is a
  dot and the meeting is a post — they are never the same mark, because one
  is a commitment and the other is a meeting.
- **Every row names the mark it draws.** The row's label carries a small
  glyph of its own mark, so a row says what it holds before it is read.
- **Today is a rule in ink over a soft band.** It runs through every row at
  once, so the whole chart is read against one moment. The band says which
  moment it is before the eye counts pixels, and the legend names the date.
- The legend says what the marks are, in the app's own hand — the board
  never asks the reader to guess what a shape means.
- **Under the chart, the same thing in words.** The milestone list says the
  period, the progress and the cards that belong; the calendar list says the
  meetings. A chart nobody can read as text is a picture, not a surface.

## Rules

- One accent: the primary action, the current selection, the focus ring, the unread
  count, links and mentions, and your own message bubble. It is never decoration.
- No decorative status dots before a label; presence is a live state chip on an avatar.
- No emoji as an icon; one icon set (lucide) for the whole app.
- Labels are the body face, a step smaller, sentence case, untracked.
- A surface is told apart by light falling on it — sheen, rim, recess — not by a
  border alone.
- **Nothing loses its ground under the pointer.** A hover may change a
  surface, but the label on it keeps at least 4.5:1 — in both themes. The
  check that keeps this true is `scripts/check-contrast.py`.
- A button is ours: no platform chrome, no platform ink. A control that
  forgets its own background wears the browser's grey plate, and its label
  ends up printed on a colour nobody chose.
- A reaction is a number until you ask who. Hovering one names the people
  behind it, on a small strip of the ink band — a label, printed like the
  labels on a shelf. It turns below the chip when the chip is near the top of
  the list.
- **A destructive action asks in a dialog, never in a strip inside the
  page.** The question names the thing and the consequence, the answer
  lands on 취소, and the risky key is the one that has to be reached for.
- Every region that loads data has four states: loading, empty, error, full.

## Exports

`desktop/src/styles/tokens.css` — CSS custom properties on `:root`, with a derived
`[data-theme="dark"]` block. The app has no Tailwind, no CSS-in-JS and no component
library: the utility layer at the bottom of `app.css` is the only other CSS.
