"""Pre-seeded project templates for quick starts."""

TEMPLATES: list[dict] = [
    {
        "id": "noir-detective",
        "title": "Shadows of Crescent City",
        "description": "A hardboiled detective navigates a rain-soaked city of corruption and intrigue.",
        "genre": "Film Noir",
        "premise": "A disgraced detective takes one last case — finding a missing jazz singer — only to uncover a conspiracy that reaches the highest levels of city government.",
        "tone": "moody, atmospheric, cynical with moments of dark humor",
        "visual_style": "Film noir, high contrast black and white with deep shadows, rain-slicked streets reflecting neon, Dutch angles, cigarette smoke curling through shafts of light",
        "setting": "1940s fictional American city, perpetual rain, art deco architecture crumbling at the edges, jazz clubs and back alleys",
        "characters": [
            {
                "name": "Jack Morrow",
                "role": "protagonist",
                "backstory": "Former police detective who was thrown off the force for refusing to cover up a murder. Now works as a PI out of a cramped office above a noodle shop.",
                "visual_description": "Weathered man in his 40s, sharp jawline, five o'clock shadow, rumpled trench coat, fedora pulled low, tired eyes that miss nothing",
                "voice": "en-US-GuyNeural",
                "voice_notes": "Low, gravelly, world-weary. Speaks in clipped sentences.",
            },
            {
                "name": "Vivienne LaRoux",
                "role": "deuteragonist",
                "backstory": "Jazz singer at The Blue Gardenia club who vanished three days ago. More than she seems — she's been secretly documenting the mayor's dealings.",
                "visual_description": "Striking woman in her 30s, dark wavy hair, red lipstick, sequined evening gown, knowing eyes, an air of danger and elegance",
                "voice": "en-US-AriaNeural",
                "voice_notes": "Smoky, confident, slightly breathless. Sings like an angel, lies like a professional.",
            },
            {
                "name": "Chief Holloway",
                "role": "antagonist",
                "backstory": "Police chief who runs the city's protection rackets. Charming in public, ruthless in private. The man who had Jack fired.",
                "visual_description": "Broad-shouldered man in his 50s, slicked-back silver hair, expensive suit, cigar always in hand, cold smile that never reaches his eyes",
                "voice": "en-GB-RyanNeural",
                "voice_notes": "Smooth, authoritative, menacing undertone.",
            },
        ],
        "locations": [
            {
                "name": "The Blue Gardenia",
                "description": "A smoky jazz club with velvet curtains, a curved mahogany bar, stage spotlights cutting through haze, intimate round tables with candles",
            },
            {
                "name": "Jack's Office",
                "description": "A cramped second-floor PI office, frosted glass door with peeling gold lettering, venetian blinds casting striped shadows, overflowing ashtray, bottle of rye in the desk drawer",
            },
            {
                "name": "The Waterfront",
                "description": "Fog-shrouded docks at night, cargo ships creaking against wooden piers, distant foghorn, puddles reflecting yellow dock lights, smell of salt and diesel",
            },
        ],
    },
    {
        "id": "space-frontier",
        "title": "The Last Outpost",
        "description": "A ragtag crew on a remote space station discovers a signal that changes everything.",
        "genre": "Sci-Fi",
        "premise": "The crew of Outpost Kepler-9, humanity's most distant station, intercepts an alien signal. As they decode it, they realize it's a warning — and something is already on its way.",
        "tone": "tense, awe-inspiring, claustrophobic isolation with bursts of wonder",
        "visual_style": "Retro-futuristic sci-fi, warm CRT monitor glows against cold metal corridors, starfields through scratched viewports, analog switches and holographic displays, Alien meets Cowboy Bebop",
        "setting": "Deep space outpost at the edge of explored territory, 2340s, cramped corridors and vast observation decks overlooking nebulae",
        "characters": [
            {
                "name": "Commander Aya Osei",
                "role": "protagonist",
                "backstory": "Decorated military officer who chose this remote posting to escape the politics of the inner colonies. Calm under pressure but haunted by a rescue mission that went wrong.",
                "visual_description": "Athletic woman in her late 30s, close-cropped hair, dark skin, utility jumpsuit with commander patches, determined expression, small scar above left eyebrow",
                "voice": "en-GB-SoniaNeural",
                "voice_notes": "Measured, authoritative, warm when she lets her guard down.",
            },
            {
                "name": "Dr. Emil Vasic",
                "role": "deuteragonist",
                "backstory": "Xenolinguist who has spent his career preparing for a moment like this. Brilliant but socially awkward, driven by pure scientific curiosity.",
                "visual_description": "Thin man in his 50s, wire-rim glasses, unkempt gray hair, lab coat over a worn sweater, perpetually distracted expression, ink-stained fingers",
                "voice": "en-IE-ConnorNeural",
                "voice_notes": "Excitable when talking about the signal, mumbles to himself, Eastern European accent.",
            },
            {
                "name": "Renko",
                "role": "supporting",
                "backstory": "Station mechanic and former smuggler. Knows every bolt and wire of the outpost. Doesn't trust the signal or the people decoding it.",
                "visual_description": "Stocky person in their 30s, oil-streaked coveralls, buzz cut, prosthetic left arm with visible mechanical joints, skeptical squint, tool belt always on",
                "voice": "en-AU-NatashaNeural",
                "voice_notes": "Blunt, sarcastic, speaks in short practical sentences.",
            },
        ],
        "locations": [
            {
                "name": "Command Bridge",
                "description": "Circular room with wraparound viewport showing stars, banks of glowing monitors, holographic tactical display in the center, captain's chair overlooking the crew stations",
            },
            {
                "name": "Signal Lab",
                "description": "Cluttered research bay with waveform displays on every screen, alien symbols projected on a whiteboard, coffee cups and data tablets scattered everywhere, soft blue ambient lighting",
            },
            {
                "name": "Observation Deck",
                "description": "A glass-domed room at the top of the station, unobstructed 180-degree view of a purple nebula, a single bench, the quietest place on the station",
            },
        ],
    },
    {
        "id": "folklore-horror",
        "title": "The Hollow",
        "description": "A village unravels when ancient folklore turns out to be terrifyingly real.",
        "genre": "Folk Horror",
        "premise": "A folklorist arrives in an isolated English village to document dying traditions. She discovers the villagers still practice old rituals — and the thing they appease in the woods is waking up.",
        "tone": "creeping dread, pastoral beauty hiding something rotten, unsettling rather than shocking",
        "visual_style": "Midsommar meets over the garden wall, golden autumn light through ancient trees, fog rolling over green fields, rustic stone buildings with strange carvings, uncanny stillness",
        "setting": "Remote English village surrounded by ancient woodland, present day but feels centuries old, no phone signal, one road in and out",
        "characters": [
            {
                "name": "Dr. Seren Cole",
                "role": "protagonist",
                "backstory": "University folklorist recording oral histories for her thesis. Rational and curious. Doesn't believe in the supernatural — until she has no choice.",
                "visual_description": "Woman in her early 30s, auburn hair often pulled back, warm-toned practical clothing, field notebook always in hand, expressive eyes that shift from curiosity to fear",
                "voice": "en-GB-SoniaNeural",
                "voice_notes": "Educated, warm, increasingly strained as events unfold.",
            },
            {
                "name": "Arthur Blackwell",
                "role": "deuteragonist",
                "backstory": "The village publican, seemingly friendly and helpful. His family has been the village's link to the outside world for generations — and its gatekeeper.",
                "visual_description": "Burly man in his 60s, ruddy cheeks, flat cap, waxed jacket, kind smile that doesn't always match his eyes, thick hands scarred from woodwork",
                "voice": "en-GB-RyanNeural",
                "voice_notes": "Warm West Country accent, avuncular, drops to a careful whisper when certain topics come up.",
            },
            {
                "name": "The Green Man",
                "role": "antagonist",
                "backstory": "The entity in the woods. Part of the land itself. Fed by centuries of offering. Patient. Hungry.",
                "visual_description": "Towering figure of twisted branches and moss, antler crown of living wood, hollow eye sockets glowing faint green, bark-like skin with leaves growing from it, moves with unnatural fluidity",
                "voice": "en-IE-ConnorNeural",
                "voice_notes": "Deep, resonant, inhuman. Speaks rarely. When it does, the words seem to come from the trees themselves.",
            },
        ],
        "locations": [
            {
                "name": "The Stag & Ivy",
                "description": "A centuries-old village pub with low oak beams, a roaring hearth, hunting trophies on the walls, amber light from oil lamps, locals who go quiet when strangers enter",
            },
            {
                "name": "The Standing Stones",
                "description": "A circle of weathered stones on a hilltop above the village, lichen-covered, strange symbols worn almost smooth, morning mist pooling between them, an unnatural silence",
            },
            {
                "name": "Blackwell Wood",
                "description": "Ancient dense forest of twisted oaks and yews, dappled light barely penetrating the canopy, paths that seem to shift, animal bones hung from branches with twine, a persistent feeling of being watched",
            },
        ],
    },
]
