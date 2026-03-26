import json
import math
import re
from pathlib import Path

def int_to_hebrew(n):
    if n == 15: return 'טו'
    if n == 16: return 'טז'
    res = ""
    for val, char in [(400, 'ת'), (300, 'ש'), (200, 'ר'), (100, 'ק'),
                      (90, 'צ'), (80, 'פ'), (70, 'ע'), (60, 'ס'), (50, 'נ'), (40, 'מ'), (30, 'ל'), (20, 'כ'), (10, 'י')]:
        while n >= val:
            res += char
            n -= val
    if n > 0:
        letters = {1: 'א', 2: 'ב', 3: 'ג', 4: 'ד', 5: 'ה', 6: 'ו', 7: 'ז', 8: 'ח', 9: 'ט'}
        res += letters[n]
    return res

def id_for_page(n):
    return f"page_{n}"

TOTAL_HEIGHT_PT = 626
HEADER_HEIGHT = 15
SEP_HEIGHT = 15
COL_HEADER_HEIGHT = 15
BASELINE_10PT = 13.5
CHARS_PER_LINE_10PT = 47
BASELINE_12PT = 16.0
CHARS_PER_LINE_12PT = 95

def estimate_text_height(text, font_size="10pt"):
    if not text: return 0
    cpl = CHARS_PER_LINE_10PT if font_size == "10pt" else CHARS_PER_LINE_12PT
    bl = BASELINE_10PT if font_size == "10pt" else BASELINE_12PT
    para_skip = 3 if font_size == "10pt" else 5
    
    paragraphs = text.split('\n\n')
    height = 0
    count = 0
    for p in paragraphs:
        p = p.strip()
        if not p: continue
        lines = math.ceil(len(p) / cpl)
        if lines == 0: lines = 1
        height += lines * bl + para_skip
        count += 1
    return height - para_skip if count > 0 else 0

def split_text_by_height(text, max_add_pt, font_size="10pt"):
    if max_add_pt <= 0 or not text:
        return "", text
        
    cpl = CHARS_PER_LINE_10PT if font_size == "10pt" else CHARS_PER_LINE_12PT
    bl = BASELINE_10PT if font_size == "10pt" else BASELINE_12PT
    para_skip = 3 if font_size == "10pt" else 5
    
    paragraphs = text.split('\n\n')
    current_height = 0
    kept_paras = []
    rem_paras = []
    
    for i, p in enumerate(paragraphs):
        p = p.strip()
        if not p: continue
        
        lines = math.ceil(len(p) / cpl)
        if lines == 0: lines = 1
        p_height = lines * bl + (para_skip if kept_paras else 0)
        
        if current_height + p_height <= max_add_pt:
            kept_paras.append(p)
            current_height += p_height
        else:
            sentences = re.split(r'(?<=\. )', p)
            kept_sentences = []
            rem_sentences = []
            
            for s in sentences:
                s_len = len(''.join(kept_sentences) + s)
                s_lines = math.ceil(s_len / cpl)
                if s_lines == 0: s_lines = 1
                s_height = s_lines * bl + (para_skip if kept_paras else 0)
                
                if current_height + s_height <= max_add_pt:
                    kept_sentences.append(s)
                else:
                    rem_sentences.append(s)
            
            if kept_sentences:
                kept_paras.append(''.join(kept_sentences).strip())
                rem_paras.append(''.join(rem_sentences).strip())
            else:
                rem_paras.append(p)
            
            rem_paras.extend([x for x in paragraphs[i+1:] if x.strip()])
            break
            
    return '\n\n'.join(kept_paras), '\n\n'.join(rem_paras)

def get_l_shape_content(avail_height_pt, makor_pending, tzinor_pending):
    m_paras = [p for p in (makor_pending.split('\n\n') if makor_pending else []) if p.strip()]
    t_paras = [p for p in (tzinor_pending.split('\n\n') if tzinor_pending else []) if p.strip()]
    
    m_text = ""
    t_text = ""
    
    while m_paras or t_paras:
        hm = estimate_text_height(m_text, "10pt")
        ht = estimate_text_height(t_text, "10pt")
        
        if not m_paras and not t_paras:
            break
            
        pull_makor = False
        if hm <= ht and m_paras:
            pull_makor = True
        elif ht < hm and t_paras:
            pull_makor = False
        elif m_paras:
            pull_makor = True
        else:
            pull_makor = False
            
        if pull_makor:
            p = m_paras[0]
            max_hm = 2 * avail_height_pt - ht - 4 * BASELINE_10PT
            avail_for_new = max_hm - hm
            if avail_for_new <= 0:
                break
                
            kept, rem = split_text_by_height(p, avail_for_new, "10pt")
            if kept:
                m_text = m_text + ("\n\n" if m_text else "") + kept
                m_paras.pop(0)
                if rem:
                    m_paras.insert(0, rem)
                    break
            else:
                break
        else:
            p = t_paras[0]
            max_ht = 2 * avail_height_pt - hm - 4 * BASELINE_10PT
            avail_for_new = max_ht - ht
            if avail_for_new <= 0:
                break
                
            kept, rem = split_text_by_height(p, avail_for_new, "10pt")
            if kept:
                t_text = t_text + ("\n\n" if t_text else "") + kept
                t_paras.pop(0)
                if rem:
                    t_paras.insert(0, rem)
                    break
            else:
                break
                
    return m_text, '\n\n'.join(m_paras), t_text, '\n\n'.join(t_paras)

def main():
    base_dir = Path("/home/user/workspace/sefer-engine")
    input_file = base_dir / "content" / "unpaginated_input.json"
    output_file = base_dir / "content" / "test_pages.json"
    
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    main_intro_rem = data['content'].get('main_intro', '')
    sections_queue = data['content'].get('sections', [])
    
    makor_paras = []
    for m in data['content'].get('makor_entries', []):
        text = m['text']
        if m.get('id') and m.get('ref'):
            text = f"{m['id']}. {m['ref']}: {text}"
        makor_paras.extend(text.split('\n\n'))
    makor_pending = '\n\n'.join(makor_paras)
    
    tzinor_paras = []
    for t in data['content'].get('tzinor_entries', []):
        text = t['text']
        if t.get('marker'):
            text = f"{t['marker']} {text}"
        tzinor_paras.extend(text.split('\n\n'))
    tzinor_pending = '\n\n'.join(tzinor_paras)
    
    pages = []
    page_num = 6
    
    while main_intro_rem or sections_queue or makor_pending.strip() or tzinor_pending.strip():
        avail_height = TOTAL_HEIGHT_PT - HEADER_HEIGHT
        
        page = {
            "id": id_for_page(page_num),
            "page_display": int_to_hebrew(page_num),
            "header": {
                "left": "שלמה",
                "center_left": data['metadata'].get('gate', ''),
                "center_right": "שפע",
                "right": int_to_hebrew(page_num)
            },
            "main_text": "",
            "main_text_continuation": "",
            "section_marker": "",
            "section_title": "",
            "section_number": "",
            "section_text": "",
            "makor_title": "מקור השפע",
            "makor_text": "",
            "tzinor_title": "צינור השפע",
            "tzinor_text": ""
        }
        
        if main_intro_rem:
            kept, rem = split_text_by_height(main_intro_rem, avail_height - SEP_HEIGHT - COL_HEADER_HEIGHT, "12pt")
            page['main_text'] = kept
            main_intro_rem = rem
            avail_height -= estimate_text_height(kept, "12pt")
            
        if not main_intro_rem and sections_queue:
            sec = sections_queue[0]
            sec_title = sec.get('title', '')
            sec_num = sec.get('number', '')
            sec_text = sec.get('text', '')
            
            pfx = f"{sec_num}. " if sec_num else ""
            sec_text_full = pfx + sec_text if not sec_text.startswith(pfx) else sec_text
            
            title_h = 18 if sec_title else 0
            text_h = estimate_text_height(sec_text_full, "12pt")
            
            if title_h + text_h <= avail_height - SEP_HEIGHT - COL_HEADER_HEIGHT:
                page['section_title'] = sec_title
                page['section_number'] = sec_num
                page['section_text'] = sec_text
                avail_height -= (title_h + text_h)
                sections_queue.pop(0)
            else:
                if title_h < avail_height - SEP_HEIGHT - COL_HEADER_HEIGHT:
                    kept, rem = split_text_by_height(sec_text, avail_height - title_h - SEP_HEIGHT - COL_HEADER_HEIGHT, "12pt")
                    if kept:
                        page['section_title'] = sec_title
                        page['section_number'] = sec_num
                        page['section_text'] = kept
                        avail_height -= (title_h + estimate_text_height(kept, "12pt"))
                        sections_queue[0] = {
                            "number": "",
                            "title": "",
                            "text": rem
                        }
        
        avail_height -= (SEP_HEIGHT + COL_HEADER_HEIGHT)
        
        if avail_height > 0:
            m_text, m_rem, t_text, t_rem = get_l_shape_content(avail_height, makor_pending, tzinor_pending)
            page['makor_text'] = m_text
            page['tzinor_text'] = t_text
            makor_pending = m_rem
            tzinor_pending = t_rem
            
        pages.append(page)
        page_num += 1

    output_data = {
        "metadata": data['metadata'],
        "pages": pages
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
        
    print(f"Paginator complete. Generated {len(pages)} pages.")

if __name__ == '__main__':
    main()