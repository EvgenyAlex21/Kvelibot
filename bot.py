import re
from datetime import datetime
from collections import defaultdict
from rapidfuzz import fuzz, process
from address_data import DISTRICTS, SYNONYMS, ROLE_MAP

def normalize(text: str) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r'[()\[\]{}]', ' ', text)
    text = re.sub(r'[-–—]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    text = text.replace('ё', 'е')
    return text.strip()

def build_address_index():
    index = {}
    for district, addresses in DISTRICTS.items():
        for addr in addresses:
            norm = normalize(addr)
            index[norm] = district
            short = re.sub(r'\b(проспект|бульвар|улица|ул\.?|пр\.?|б-р|музыканта)\b', '', norm).strip()
            short = re.sub(r'\s+', ' ', short)
            if short and short != norm:
                index[short] = district
    return index

ADDRESS_INDEX = build_address_index()

def find_district(address_str: str) -> str | None:
    if not address_str:
        return None
    norm = normalize(address_str)

    if norm in ADDRESS_INDEX:
        return ADDRESS_INDEX[norm]

    for syn, full in SYNONYMS.items():
        if syn in norm:
            candidate = norm.replace(syn, normalize(full))
            if candidate in ADDRESS_INDEX:
                return ADDRESS_INDEX[candidate]
            for addr_norm, dist in ADDRESS_INDEX.items():
                if syn in addr_norm or normalize(full) in addr_norm:
                    if fuzz.partial_ratio(norm, addr_norm) > 68:
                        return dist

    choices = list(ADDRESS_INDEX.keys())
    result = process.extractOne(norm, choices, scorer=fuzz.token_set_ratio, score_cutoff=62)
    if result:
        return ADDRESS_INDEX[result[0]]
    result = process.extractOne(norm, choices, scorer=fuzz.partial_ratio, score_cutoff=72)
    if result:
        return ADDRESS_INDEX[result[0]]

    if any(x in norm for x in ['богдан', 'б.х', 'бх', 'кошкино']):
        return "БОГДАНКА"
    if 'кугеси' in norm or 'советская' in norm:
        return "КУГЕСИ"
    if 'питер' in norm:
        return "СЗР"
    if 'черныш' in norm:
        return "ЮЗР"
    if 'неон' in norm:
        return "СЗР"
    return None

def get_time_slots() -> list[str]:
    weekday = datetime.now().weekday()
    if weekday in (4, 5):
        return ["22:00", "00:00", "01:00"]
    return ["22:00", "23:00"]

def get_default_main_time() -> str:
    return get_time_slots()[-1]


def get_delivery_default_time() -> str:
    return "22:00"


def get_closing_times() -> tuple[str, str]:
    slots = get_time_slots()
    return slots[0], slots[-1]

STREET_HINTS = {
    'московский', 'эгерский', 'элгера', 'эльгера', 'трактор', 'ленкома', 'кадыкова',
    'хевешская', 'хевесшкая', 'обиковская', 'хузангая', 'мира', 'гражданская',
    'энтузиастов', 'гагарина', 'байдукова', 'байдула', 'николаева', 'президентский',
    'ярославская', 'карла', 'макса', 'маркса', 'октября', 'крутовой',
    'первомайская', 'дементьева', 'кошкино', 'богданка', 'советская',
    'талвира', 'водопроводная', 'гузовского', 'лукина', 'афанасьева',
    'кривова', 'универ', 'университетская', 'питер', 'тц', 'кугеси',
    'чернышевского', 'черныш', 'ост', 'остановка', '50', 'лет', 'жени',
    'кукшумская', 'байдула', 'декабристов', 'лумумбы', 'чапаева', 'энгельса',
    'ярмарочная', 'яроморочная', 'бажова', 'сапожникова', 'строителей',
    'тракторостроителей', 'яковлева', 'музыканта', 'галкина', 'ельниковский',
    'пионерская', 'челомея', 'каролина', 'хмельницкого', 'миттова', 'залка',
    'королева', 'юго', 'западный', 'волжский', 'ильенко', 'горького', 'маркова',
    'павлова', 'пирогова', 'неон', 'пятилетки', 'б.х', 'бх', 'филипа', 'мичмана', 
    'социалистическая', 'шумилова', 'больничный', 'стрелковая', 'стрелковач', 'дивизия', 
    'восточная', 'лубумба', 'лумумбы', 'лумумба', 'гражд'
}

def parse_person_line(line: str) -> tuple[str | None, str | None]:
    line = line.strip()
    if not line:
        return None, None

    if re.search(r'\s*[-–—:]\s*', line):
        parts = re.split(r'\s*[-–—:]\s*', line, maxsplit=1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            name = parts[0].strip()
            addr = parts[1].strip()
            addr = re.sub(r'\s*\(до\s*\d+\)\s*$', '', addr, flags=re.I).strip()
            name_is_latin = bool(re.match(r'^[A-Za-z0-9_.]+$', name))
            words_a = addr.split()
            if name_is_latin and len(words_a) >= 2:
                w0 = words_a[0]
                rest = ' '.join(words_a[1:])
                rest_low = rest.lower().replace('ё', 'е')
                if re.search(r'[А-Яа-яЁё]', w0) and (
                    any(len(h) > 3 and h in rest_low for h in STREET_HINTS) or re.search(r'\d', rest)
                ):
                    name = w0
                    addr = rest
            return name, addr

    if re.match(r'^(\d+\s*(т|эт|этаж|терраса)|ранер|ранеры|ранеры)', line, re.I):
        return None, None

    words = line.split()
    if len(words) == 1:
        return None, line

    addr_start = None
    for i, w in enumerate(words):
        w_low = w.lower().replace('ё', 'е')
        is_street = w_low in STREET_HINTS or any(
            (h == w_low) or (len(h) > 3 and h in w_low) for h in STREET_HINTS
        )
        if re.search(r'\d', w) or is_street:
            addr_start = i
            break

    if addr_start is not None and addr_start > 0:
        name = ' '.join(words[:addr_start])
        addr = ' '.join(words[addr_start:])
        addr = re.sub(r'\s*\(до\s*\d+\)\s*$', '', addr, flags=re.I).strip()
        return name.strip(), addr.strip()
    elif addr_start == 0:
        return None, line

    if len(words) >= 2:
        return words[0], ' '.join(words[1:])
    return None, line

def extract_inline_time(text: str) -> str | None:
    m = re.search(r'\(до\s*(\d{1,2})\)', text, re.I)
    if m:
        h = int(m.group(1))
        if h == 22: return "22:00"
        if h in (0,): return "00:00"
        if h == 1: return "01:00"
        if h == 23: return "23:00"
    m = re.search(r'до\s*(\d{1,2})', text, re.I)
    if m:
        h = int(m.group(1))
        if h == 22: return "22:00"
        if h == 0: return "00:00"
        if h == 1: return "01:00"
        if h == 23: return "23:00"
    return None

def parse_input(text: str) -> list[dict]:
    text = re.sub(r'\[\d{2}\.\d{2}\.\d{4}\s+\d{1,2}:\d{2}\]\s*', '', text)

    lines = text.strip().splitlines()
    people = []
    current_role = None
    current_time = None
    main_time = get_default_main_time()

    section_keywords = {
        'клининг': 'клин', 'развоз': 'офф', 'раннер': 'офф-ран',
        'ранеры': 'офф-ран', 'ранеры': 'офф-ран', 'караоке': 'кар',
        'доставка': 'дост', 'кухня': 'кух', 'хостес': 'хост',
        'офики': 'офф', 'вип': 'офф', 'бар': 'бар',
    }

    time_patterns = [
        (r'до\s*22\s*:?', '22:00'),
        (r'до\s*00\s*:?', '00:00'),
        (r'до\s*01\s*:?', '01:00'),
        (r'до\s*23\s*:?', '23:00'),
        (r'^22(:00)?\s*$', '22:00'),
        (r'^00(:00)?\s*$', '00:00'),
        (r'^01(:00)?\s*$', '01:00'),
        (r'^23(:00)?\s*$', '23:00'),
        (r'^22:00\s*$', '22:00'),
        (r'^00:00\s*$', '00:00'),
        (r'^01:00\s*$', '01:00'),
        (r'^23:00\s*$', '23:00'),
    ]

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        norm_line = normalize(line)

        is_time = False
        for pat, tval in time_patterns:
            if re.search(pat, norm_line) and len(norm_line) < 15:
                if tval == "23:00" and "01:00" in get_time_slots():
                    tval = "01:00"
                current_time = tval
                is_time = True
                break
        if is_time:
            continue

        role_found = None
        for key, role in section_keywords.items():
            if key in norm_line and len(norm_line) < 100:
                role_found = role
                break
        if role_found:
            current_role = role_found
            line2 = re.sub(
                r'^.*?(?:клининг|развоз|раннер|ранеры|ранеры|караоке|доставка|кухня|хостес|офики|вип|бар)\s*:?\s*',
                '', line, flags=re.I, count=1
            ).strip()
            m = re.search(r'^до\s*(\d{1,2})', line2, re.I)
            if m:
                h = int(m.group(1))
                if h == 22: current_time = "22:00"
                elif h == 0: current_time = "00:00"
                elif h == 1: current_time = "01:00"
                elif h == 23: current_time = "23:00"
            else:
                t_inline = extract_inline_time(line2)
                if t_inline:
                    current_time = t_inline
                else:
                    current_time = None  
            line2 = re.sub(r'^до\s*\d{1,2}\s*', '', line2, flags=re.I).strip()
            if not line2 or len(line2) < 3:
                continue
            line = line2
            norm_line = normalize(line)

        if re.match(r'^[A-Za-z][A-Za-z0-9_.]*\s*:', line) and not any(
            k in normalize(line) for k in section_keywords
        ):
            current_role = None
            after = re.sub(r'^[A-Za-z][A-Za-z0-9_.]*\s*:\s*', '', line).strip()
            if after and len(after) > 3:
                line = after
                norm_line = normalize(line)
            else:
                continue

        if line.endswith(':') and len(line) < 40:
            continue
        if re.match(r'^(\d+\s*(т|эт|этаж|терраса)|ранер|ранеры|ранеры|клининг|развоз|кухня|хостес|бар|караоке|доставка|офики|вип)\s*:?\s*$', line, re.I):
            if 'ран' in norm_line:
                current_role = 'офф-ран'
            elif any(x in norm_line for x in ['клининг']):
                current_role = 'клин'
            elif any(x in norm_line for x in ['кухн']):
                current_role = 'кух'
            elif any(x in norm_line for x in ['хостес']):
                current_role = 'хост'
            elif any(x in norm_line for x in ['бар']):
                current_role = 'бар'
            elif any(x in norm_line for x in ['караоке']):
                current_role = 'кар'
            elif any(x in norm_line for x in ['доставк']):
                current_role = 'дост'
            else:
                current_role = 'офф'
            continue
        if re.match(r'^(до\s*)?\d{1,2}(:\d{2})?\s*$', norm_line):
            continue
        if len(line) < 4:
            continue

        line = re.sub(r'^до\s*\d{1,2}\s*', '', line, flags=re.I).strip()
        if not line:
            continue

        candidates = []
        if len(line) > 35 and len(re.findall(r'\d', line)) >= 2:
            raw_parts = re.split(r'(?<=\d)\s+(?=[А-ЯЁA-Z])', line)
            parts = []
            for p in raw_parts:
                p = p.strip()
                if len(p) < 3:
                    if parts:
                        parts[-1] = parts[-1] + " " + p
                    continue
                parts.append(p)
            if not parts:
                parts = [line]
        else:
            parts = [line]

        for p in parts:
            p = p.strip()
            if not p or re.match(r'^(до\s*\d+|22|00|01|23)$', normalize(p)):
                continue
            n, a = parse_person_line(p)
            if a and len(a) > 1:
                candidates.append((n, a, p))
        if not candidates:
            continue

        for name, address, raw_p in candidates:
            if not address:
                continue
            addr_norm = normalize(address)
            if len(addr_norm) < 2:
                continue
            if re.match(r'^(до\s*)?\d{1,2}(:\d{2})?$', addr_norm):
                continue
            if addr_norm in ('клининг', 'развоз', 'кухня', 'хостес', 'бар', 'караоке',
                             'доставка', 'ранеры', 'ранер', 'офики', 'вип', 'терраса', 'этаж'):
                continue
            if any(x in addr_norm for x in ['добрый вечер', 'добрый день', 'привет', 'здравствуй', 'как дела']):
                continue
            if any(x in normalize(raw_p) for x in ['добрый вечер', 'добрый день', 'привет']):
                continue
            has_digit = bool(re.search(r'\d', address))
            has_street = any(h in addr_norm for h in STREET_HINTS) or any(s in addr_norm for s in SYNONYMS)
            if not has_digit and not has_street and len(addr_norm) < 8:
                continue

            inline_t = extract_inline_time(raw_p) or extract_inline_time(address)
            if inline_t:
                time_group = inline_t
            elif current_role == 'дост' and current_time is None:
                time_group = get_delivery_default_time()
            else:
                time_group = current_time or main_time

            address_clean = address
            address_clean = re.sub(r'\bгражд\b', 'гражданская', address_clean, flags=re.I)
            address_clean = re.sub(r'\bлубумб[аыу]?\b', 'лумумбы', address_clean, flags=re.I)
            address_clean = re.sub(r'\b50-лет\b', '50 лет октября', address_clean, flags=re.I)
            address_clean = re.sub(r'\bстрелковач\b', 'стрелковая', address_clean, flags=re.I)
            address_clean = re.sub(r'чебоксары[,\s]*', '', address_clean, flags=re.I).strip()
            address_clean = re.sub(r'\s*\([^)]*(?:чел|своим|факт|скорее)[^)]*\)?\s*', ' ', address_clean, flags=re.I).strip()
            address_clean = re.sub(r'\s+', ' ', address_clean)

            district = find_district(address_clean)
            if not district and any(x in normalize(address_clean) for x in ['богдан', 'б.х', 'бх']):
                district = 'БОГДАНКА'
            if address_clean != address:
                address = address_clean

            people.append({
                'name': name,
                'address': address,
                'district': district,
                'role': current_role,
                'time_group': time_group,
                'raw': raw_p
            })

    return people

def format_person(p: dict) -> str:
    name = p['name'] or ''
    addr = p['address']
    district = p['district'] or 'НЕОПР'
    role = p['role'] or ''
    if name:
        base = f"{name} - {addr}"
    else:
        base = addr
    result = f"{base} ({district})"
    if role:
        result += f", {role}"
    return result

def build_output(people: list[dict]) -> str:
    slots = get_time_slots()

    by_time = defaultdict(list)
    undef = []
    for p in people:
        if not p['district']:
            undef.append(p)
        else:
            by_time[p['time_group']].append(p)

    order_driver1 = ['СЗР', 'ЮЗР']
    order_driver2 = ['ЦЕНТР', 'НОВЫЙ', 'НЧК']
    order_driver3 = ['НЮР', 'КУГЕСИ']
    bog = 'БОГДАНКА'

    def group_by_district(plist):
        g = defaultdict(list)
        for p in plist:
            g[p['district']].append(p)
        return g

    def sort_people(plist):
        def key(p):
            name = (p.get('name') or '').lower().replace('ё', 'е')
            addr = (p.get('address') or '').lower().replace('ё', 'е')
            return (name, addr)
        return sorted(plist, key=key)

    def count_without_bog(groups):
        c2 = sum(len(groups.get(d, [])) for d in order_driver2)
        c3 = sum(len(groups.get(d, [])) for d in order_driver3)
        return c2, c3

    def render_district(lines, d, groups):
        if d not in groups or not groups[d]:
            return
        plist = sort_people(groups[d])
        cnt = len(plist)
        lines.append(f"-- ({cnt}) {d} --")
        lines.append("")  
        for p in plist:
            lines.append(format_person(p))
        lines.append("")  

    def render_section(groups: dict, title: str) -> list[str]:
        lines = [f"--- СПИСОК ДО {title} ---", ""] 

        for d in order_driver1:
            render_district(lines, d, groups)

        c2, c3 = count_without_bog(groups)
        bog_to_2 = c2 <= c3 

        has_d2 = any(d in groups and groups[d] for d in order_driver2) or (bog_to_2 and bog in groups and groups[bog])
        has_d3 = any(d in groups and groups[d] for d in order_driver3) or ((not bog_to_2) and bog in groups and groups[bog])

        if has_d2:
            if any(d in groups and groups[d] for d in order_driver1):
                lines.append("---------------------------------------")
                lines.append("")
            if bog_to_2:
                render_district(lines, bog, groups)
            for d in order_driver2:
                render_district(lines, d, groups)

        if has_d3:
            if has_d2 or any(d in groups and groups[d] for d in order_driver1):
                lines.append("---------------------------------------")
                lines.append("")
            if not bog_to_2:
                render_district(lines, bog, groups)
            for d in order_driver3:
                render_district(lines, d, groups)

        while lines and lines[-1] == "":
            lines.pop()
        return lines

    output = []
    first = True
    for slot in slots:
        if slot in by_time and by_time[slot]:
            if not first:
                output.append("")
                output.append("")
                output.append("")
            first = False
            groups = group_by_district(by_time[slot])
            output.extend(render_section(groups, slot))

    if undef:
        if output:
            output.append("")
            output.append("")
            output.append("")
        output.append("--- НЕОПРЕДЕЛЕНО ---")
        output.append("")
        for p in undef:
            output.append(format_person(p) + f"  [raw: {p['raw']}]")

    return "\n".join(output).strip()

def process_list(raw_text: str) -> str:
    people = parse_input(raw_text)
    if not people:
        return "Не удалось распознать ни одного человека. Проверьте формат списка."
    return build_output(people)

if __name__ == "__main__":
    sample = """
"""
    print(process_list(sample))