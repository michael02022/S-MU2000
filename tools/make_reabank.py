#!/usr/bin/env python3
# license:BSD-3-Clause
"""Genera un .reabank (REAPER / ReaMIDI) con los nombres de voces del MU2000,
leidos en tiempo de ejecucion del propio mu2000_flash.bin del usuario.

Replica en Python la logica de src/xg/voices.h (xg::voice_rom::lookup /
record_name / kit_name), que ya hace exactamente esto mismo al vuelo para
pintar el nombre del color en el LCD del panel. No incluye ningun nombre de
voz de fabrica: todo sale de los bytes del ROM que se le pase por argumento.

Uso:
    python3 tools/make_reabank.py <ruta a mu2000_flash.bin> [salida.reabank]
"""
import struct
import sys

VOICES        = 0x200ee0
VOICES_END    = 0x23cece
KIT_MAP       = 0x299fcc
KIT_NAMES     = 0x299dc0
SFX_MAP       = 0x29be58
SFX_NAMES     = 0x29bdec
GROUP_GM      = 0x283d50   # sin usar (solo generamos el modo XG, ver mas abajo)
GROUP_XG      = 0x283950
GROUP_LSB0    = 0x2839d0
GROUP_LSB1    = 0x283a50
GROUP_LSB77   = 0x283ad0
GROUP_LSBC9_0 = 0x292640
GROUP_LSBC9_1 = 0x2926c0
VOICE_TABLE   = 0x267f50


def trim(s: bytes) -> str:
    return s.rstrip(b" \x00").decode("latin1")


class VoiceRom:
    def __init__(self, rom: bytes):
        self.rom = rom
        self.ok = (
            len(rom) == 0x400000
            and rom[VOICES + 2:VOICES + 10] == b"GrandPno"
            and rom[KIT_NAMES:KIT_NAMES + 8] == b"StandKit"
            and rom[SFX_NAMES:SFX_NAMES + 8] == b"SFXKit 1"
        )

    def group_for(self, set_: int, msb: int, lsb: int):
        """Grupo de programas para (msb, lsb) en modo XG. None si el
        firmware no define nada ahi (p.ej. msb=16, lsb<2: MSB=16 es el
        banco de capital-tone especial que el firmware trata aparte y que
        aqui todavia no se ha reproducido -- ver comentario en voices.h)."""
        if msb == 16 and lsb < 2:
            return None
        kind = self.rom[GROUP_XG + msb]
        if kind == 0:
            base = GROUP_LSB1 if set_ else GROUP_LSB0
            return self.rom[base + lsb]
        if kind == 77:
            return self.rom[GROUP_LSB77 + lsb]
        if kind == 0xC9:
            base = GROUP_LSBC9_1 if set_ else GROUP_LSBC9_0
            return self.rom[base + lsb]
        return kind

    def record_name(self, rec: int) -> str:
        if rec < VOICES or rec + 12 > VOICES_END:
            return ""
        return trim(self.rom[rec + 2:rec + 12])

    def records_for_group(self, group: int):
        """Direccion de registro (0 si no existe) para cada uno de los 128
        programas de un grupo. Dos programas con la MISMA direccion son,
        literalmente, la misma voz (no una variacion: el firmware no llego
        a redefinir ese programa para este grupo y el dato cae en el mismo
        sitio que el grupo del que salio)."""
        out = []
        for prog in range(128):
            slot = VOICE_TABLE + group * 512 + prog * 4
            if slot + 4 > len(self.rom):
                out.append(0)
                continue
            off = struct.unpack(">I", self.rom[slot:slot + 4])[0]
            rec = VOICES + off * 2
            out.append(rec if VOICES <= rec and rec + 16 <= VOICES_END else 0)
        return out

    def names_for_group(self, group: int):
        return [self.record_name(r) if r else "" for r in self.records_for_group(group)]

    def kit_name(self, msb: int, prog: int) -> str:
        map_ = KIT_MAP if msb == 127 else SFX_MAP
        names = KIT_NAMES if msb == 127 else SFX_NAMES
        idx = self.rom[map_ + (prog & 0x7F)]
        s = trim(self.rom[names + idx * 12: names + idx * 12 + 8])
        return "" if s == "SilenKit" else s


def build_reabank(vr: VoiceRom, set_: int = 1):
    lines = [
        "// Generado localmente por tools/make_reabank.py a partir del",
        "// mu2000_flash.bin del propio usuario -- ningun nombre de voz de",
        "// fabrica esta incluido en el repositorio S-MU2000.",
        "",
    ]

    # Bancos melodicos, modo XG (MSB 0-125). Solo se emite un Bank nuevo
    # cuando el LSB hace que el firmware cambie de grupo de programas
    # (capital tone fallback: LSB no definidos repiten el grupo anterior).
    # Muchos MSB no tienen tabla propia y caen en la misma tabla generica
    # por LSB (kind == 0 en el firmware): dedupe global por contenido para
    # no repetir el mismo banco 128 nombres bajo decenas de MSB distintos.
    #
    # Ademas, dentro de un MSB con variaciones reales (Stereo, Detune,
    # Octave...), casi todos los programas de cada variacion son en realidad
    # el mismo registro que el primer LSB de ese MSB (el firmware solo
    # redefine unos pocos programas por variacion; el resto "cae" en el
    # mismo dato de siempre). Esos no son presets nuevos, son el mismo
    # preset repetido: se comparan por DIRECCION de registro (no por nombre)
    # contra la base de su propio MSB y se omiten si no cambian nada.
    seen_full = set()
    for msb in range(126):
        prev_group = object()  # distinto de cualquier int o None
        base_recs = None
        for lsb in range(128):
            group = vr.group_for(set_, msb, lsb)
            if group == prev_group:
                continue
            prev_group = group
            if group is None:
                continue
            recs = vr.records_for_group(group)
            names = tuple(vr.record_name(r) if r else "" for r in recs)
            if not any(names):
                continue
            if names in seen_full:
                continue   # banco identico, ya salio bajo otro MSB
            seen_full.add(names)

            if base_recs is None:
                # primer contenido realmente nuevo de este MSB: es la base,
                # se muestra completo
                entries = [(p, nm) for p, nm in enumerate(names) if nm]
                base_recs = recs
            else:
                # variacion de LSB dentro del mismo MSB: solo los programas
                # que de verdad cambiaron respecto a la base de este MSB
                entries = [(p, nm) for p, (nm, r) in enumerate(zip(names, recs))
                           if nm and r != base_recs[p]]
                if not entries:
                    continue   # esta variacion no redefine nada -> no existe como preset aparte

            lines.append(f"Bank {msb} {lsb} MU2000 {msb}.{lsb}")
            for prog, name in entries:
                lines.append(f"{prog} {name}")
            lines.append("")

    # Kits de bateria (MSB 127) y de efectos (MSB 126)
    for msb, label in ((127, "Drum Kits"), (126, "SFX Kits")):
        names = [vr.kit_name(msb, p) for p in range(128)]
        if any(names):
            lines.append(f"Bank {msb} 0 MU2000 {label}")
            for prog, name in enumerate(names):
                if name:
                    lines.append(f"{prog} {name}")
            lines.append("")

    return "\n".join(lines) + "\n"


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    rom_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else "MU2000.reabank"

    with open(rom_path, "rb") as f:
        rom = f.read()

    vr = VoiceRom(rom)
    if not vr.ok:
        print("El ROM no coincide con la version que este script conoce "
              "(MU2000 EX firmware v2.01). No se genera nada.", file=sys.stderr)
        return 1

    text = build_reabank(vr)
    with open(out_path, "w", encoding="latin1") as f:
        f.write(text)
    banks = text.count("Bank ")
    print(f"{out_path}: {banks} bancos escritos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
