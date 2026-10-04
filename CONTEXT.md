# Emoji Dataset

Emoji artwork for terminal users, including use with notification tools.

## Language

**Emoji**:
A character or sequence of characters identified by Unicode, independently of its visual appearance.

**Emoji index**:
The Unicode-based catalog of emojis for which vendor artwork can be associated.
_Avoid_: Image source

**Vendor**:
The provider of an emoji design, such as Apple, Google, or Twitter.
_Avoid_: Family

**Artwork**:
A vendor's visual representation of an emoji. Different vendors can supply different artwork for the same emoji.

**Image source**:
The location from which vendor artwork is obtained, such as Emojipedia. The image source and the vendor are distinct concepts.

**Shortcode**:
A textual alias used to select an emoji from the command line, independently of the selected vendor's artwork.

**Skin tone**:
A variation of a supported human emoji selected independently of its base shortcode. Some multi-person emojis support more than one skin tone in a single sequence.

**Default vendor**:
The installed vendor selected when no vendor override is supplied. Initially, it is the first vendor successfully installed.

**Default skin tone**:
A saved preference applied to emojis that support skin-tone variations when no per-request tone is supplied.

**Artwork preview**:
A smaller rendering of vendor artwork, distinct from its original image. It depicts the same emoji and vendor design.
