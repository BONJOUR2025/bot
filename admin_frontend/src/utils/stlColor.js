/**
 * Per-facet colour out of a binary STL.
 *
 * three's STLLoader only reads colour when the 80-byte header contains a
 * literal "COLOR=" tag (the Magics convention). Plenty of binary STLs carry
 * colour in the per-facet attribute word without that tag (the
 * VisCAM/SolidView convention), and three renders those grey with no warning.
 * So the attribute word is decoded here directly, and what was found is
 * reported back so the UI can say it out loud instead of guessing.
 *
 * The two conventions disagree about the top bit: VisCAM sets it to mean
 * "this facet's colour is valid", Magics clears it to mean the same. They are
 * told apart by the header tag, and when neither applies the attribute is only
 * treated as colour if it actually varies between facets -- a single constant
 * word repeated on every triangle is what several scanners write as filler,
 * and painting the whole model one arbitrary colour from it would be inventing
 * data. (Measured on this project's own scans: 110040 triangles all carrying
 * the identical word 0x1871 with no COLOR= tag -- filler, not colour.)
 *
 * Returns { colors, note }: `colors` is a Float32Array of per-vertex RGB ready
 * for a `color` BufferAttribute, or null when the file has none; `note` is a
 * short human-readable summary for the UI.
 */

const NONE = (note) => ({ colors: null, note });

function isAsciiStl(buffer) {
  const head = new Uint8Array(buffer, 0, Math.min(5, buffer.byteLength));
  return String.fromCharCode(...head).toLowerCase() === 'solid';
}

function decode555(word) {
  return [
    (word & 0x1f) / 31,
    ((word >> 5) & 0x1f) / 31,
    ((word >> 10) & 0x1f) / 31,
  ];
}

export function extractStlColors(buffer) {
  if (buffer.byteLength < 84) return NONE('файл слишком мал');
  if (isAsciiStl(buffer)) return NONE('ASCII STL — формат не хранит цвет');

  const view = new DataView(buffer);
  const triangles = view.getUint32(80, true);
  if (buffer.byteLength < 84 + triangles * 50) return NONE('в файле нет цвета');

  let headerText = '';
  for (let i = 0; i < 80; i += 1) headerText += String.fromCharCode(view.getUint8(i));
  const tagAt = headerText.indexOf('COLOR=');
  let defaultColor = null;
  if (tagAt >= 0 && tagAt + 9 < 80) {
    defaultColor = [
      view.getUint8(tagAt + 6) / 255,
      view.getUint8(tagAt + 7) / 255,
      view.getUint8(tagAt + 8) / 255,
    ];
  }

  const words = new Uint16Array(triangles);
  let anyTopBit = false;
  for (let i = 0; i < triangles; i += 1) {
    const w = view.getUint16(84 + i * 50 + 48, true);
    words[i] = w;
    if (w & 0x8000) anyTopBit = true;
  }
  const distinct = new Set(words).size;

  let validIf;
  let convention;
  if (defaultColor) { validIf = (w) => (w & 0x8000) === 0; convention = 'Magics'; }
  else if (anyTopBit) { validIf = (w) => (w & 0x8000) !== 0; convention = 'VisCAM'; }
  else if (distinct > 1) { validIf = () => true; convention = 'без флага'; }
  else {
    return NONE(distinct === 1 && words[0] !== 0
      ? 'в файле нет цвета: у всех граней один служебный код'
      : 'в файле нет цвета');
  }

  const colors = new Float32Array(triangles * 9);
  let coloured = 0;
  for (let i = 0; i < triangles; i += 1) {
    let rgb;
    if (validIf(words[i])) { rgb = decode555(words[i]); coloured += 1; }
    else rgb = defaultColor || [0.8, 0.8, 0.8];
    for (let v = 0; v < 3; v += 1) {
      colors[i * 9 + v * 3] = rgb[0];
      colors[i * 9 + v * 3 + 1] = rgb[1];
      colors[i * 9 + v * 3 + 2] = rgb[2];
    }
  }
  if (!coloured) return NONE('в файле нет цвета');

  const shades = new Set();
  for (let i = 0; i < triangles; i += 1) if (validIf(words[i])) shades.add(words[i]);
  return {
    colors,
    note: `цвет из файла (${convention}): ${shades.size} ${shades.size === 1 ? 'оттенок' : 'оттенков'}`,
  };
}

export default extractStlColors;
