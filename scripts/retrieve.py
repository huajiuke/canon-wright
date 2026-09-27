#!/usr/bin/env python3
'''M1 检索入口：从可验证来源定位阅读范围。只用标准库。

设计约束来自 docs/product-constitution.md 第 6 节：给不出出处的候选一律不输出。
因此每个候选都必须同时具备 id（可验证标识）、locator（定位）、obtained（获取方式），
缺任何一项即被 gate() 丢弃，并在 stderr 报告丢弃原因。

本轮只覆盖能全自动定位的两类：论文（页码级）与古籍（卷/叶级）。
现代书的页码级定位需人工回填，留待后续迭代。
'''

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = 'canon-wright/0.1 (https://github.com/huajiuke/canon-wright)'
MAILTO = os.environ.get('CANON_MAILTO', '')
ZOTERO_KEY = os.environ.get('ZOTERO_API_KEY', '')
ZOTERO_LIB = os.environ.get('ZOTERO_LIBRARY_ID', '')

WS_API = 'https://zh.wikisource.org/w/api.php?'
PAGE_NS = '104'

GRADE_RANK = {'none': 0, 'coarse': 1, 'article': 2, 'volume': 3, 'page': 4, 'leaf': 5}
MIN_GRADE = {'paper': 'page', 'classic': 'volume'}

# 宪法第 2 节第 7 条「可读完原则」的机械落实：30 分钟读不完的单元不予通过。
# 文言文按 30 分钟约 4000 字估算，UTF-8 汉字约 3 字节，另留出标记与标点的余量。
READABLE_BYTES = 12000

_LAST_CALL = {}


def throttle(host, interval):
    previous = _LAST_CALL.get(host, 0.0)
    wait = interval - (time.monotonic() - previous)
    if wait > 0:
        time.sleep(wait)
    _LAST_CALL[host] = time.monotonic()


def fetch_json(url, host, interval=1.0, retries=3, headers=None):
    request_headers = {'User-Agent': UA}
    if headers:
        request_headers.update(headers)
    for attempt in range(retries):
        throttle(host, interval)
        try:
            request = urllib.request.Request(url, headers=request_headers)
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as error:
            retryable = error.code in (429, 500, 502, 503)
            if retryable and attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            raise RuntimeError('HTTP %s for %s' % (error.code, url)) from error
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError('network failure for %s: %s' % (url, error)) from error
    raise RuntimeError('exhausted retries for %s' % url)


def gate(candidates, kind, allow_article=False):
    '''宪法第 6 节硬校验：三要素不全的候选不得进入台账。'''
    floor = MIN_GRADE[kind]
    if allow_article and floor == 'page':
        floor = 'article'
    minimum = GRADE_RANK[floor]
    kept, dropped = [], []
    for item in candidates:
        missing = [key for key in ('id', 'locator', 'obtained') if not item.get(key)]
        if missing:
            dropped.append({'title': item.get('title'), 'dropped': 'missing:' + ','.join(missing)})
        elif GRADE_RANK[item.get('locator_grade', 'none')] < minimum:
            dropped.append({'title': item.get('title'), 'dropped': 'locator_below_%s' % floor})
        else:
            kept.append(item)
    for entry in dropped:
        print('dropped: %s (%s)' % (entry['title'], entry['dropped']), file=sys.stderr)
    return kept, dropped


def segment_reading_range(locator):
    pages = re.search(r'(\d+)\s*[-–]\s*(\d+)', locator or '')
    if pages:
        return int(pages.group(2)) - int(pages.group(1)) + 1
    single = re.search(r'(\d+)', locator or '')
    return 1 if single else None


def classic_grade(size):
    '''按页面体积判断这个单元能否在 30 分钟内读完。'''
    if size is None:
        return 'coarse'
    return 'volume' if size <= READABLE_BYTES else 'coarse'


def classify_page(value):
    '''区分真页码与文章号。

    不少期刊（Heritage Science、Angewandte Chemie 等）不给页码，改给文章号，
    形如 e202318026 或 9140057。把它们当页码会让 pages 谎报成 1 页，
    而文章号实际只说明「整篇」，不说明长度。
    '''
    if not value:
        return None, None
    trimmed = value.strip()
    span = re.fullmatch(r'(\d+)\s*[-–]\s*(\d+)', trimmed)
    if span:
        return '页码 %s-%s' % (span.group(1), span.group(2)), 'page'
    if re.fullmatch(r'\d{1,5}', trimmed):
        return '页码 %s' % trimmed, 'page'
    return '整篇（文章号 %s）' % trimmed, 'article'


def parse_page_title(title):
    leaf = re.search(r'/(\d+)$', title)
    volume = re.search(r'\bv\.\d+', title) or re.search(r'Volume\s+\d+', title)
    if 'Harvard drs' in title:
        edition = '哈佛藏本'
    else:
        scan = re.match(r'Page:(.+?)[,.]', title)
        edition = scan.group(1).strip() if scan else None
    return {
        'edition': edition,
        'volume_label': volume.group(0) if volume else None,
        'leaf': leaf.group(1) if leaf else None,
    }


def openalex_locator(work):
    biblio = work.get('biblio') or {}
    first, last = biblio.get('first_page'), biblio.get('last_page')
    volume, issue = biblio.get('volume'), biblio.get('issue')
    raw = '%s-%s' % (first, last) if (first and last and first != last) else first
    locator, grade = classify_page(raw)
    if locator:
        return locator, grade
    if volume and issue:
        return '整篇（卷 %s 第 %s 期，页码未收录）' % (volume, issue), 'article'
    if volume:
        return '整篇（卷 %s，页码未收录）' % volume, 'article'
    return None, 'none'


def search_paper(args):
    base = 'https://api.openalex.org/works?per-page=%d' % args.limit
    params = {'search': args.query, 'sort': 'relevance_score:desc'}
    if MAILTO:
        params['mailto'] = MAILTO
    filters = []
    language = None if args.lang == 'all' else args.lang
    if language:
        filters.append('language:%s' % language)
    if args.year_from:
        filters.append('from_publication_date:%s-01-01' % args.year_from)
    if args.year_to:
        filters.append('to_publication_date:%s-12-31' % args.year_to)
    if filters:
        params['filter'] = ','.join(filters)
    payload = fetch_json(base + '&' + urllib.parse.urlencode(params), 'api.openalex.org')

    candidates = []
    for work in payload.get('results', []):
        locator, grade = openalex_locator(work)
        open_access = work.get('open_access') or {}
        best = work.get('best_oa_location') or {}
        doi = (work.get('doi') or '').replace('https://doi.org/', '')
        candidates.append({
            'kind': 'paper',
            'title': (work.get('title') or '').strip(),
            'year': work.get('publication_year'),
            'language': work.get('language'),
            'type': work.get('type'),
            'id': doi or work.get('id'),
            'venue': ((work.get('primary_location') or {}).get('source') or {}).get('display_name'),
            'locator': locator,
            'locator_grade': grade,
            'obtained': best.get('pdf_url') or open_access.get('oa_url') or (
                'DOI 可核验，全文需机构订阅' if doi else None),
            'pages': segment_reading_range(locator) if grade == 'page' else None,
        })
    return candidates


def verify_doi(args):
    url = 'https://api.crossref.org/works/' + urllib.parse.quote(args.doi)
    if MAILTO:
        url += '?mailto=' + urllib.parse.quote(MAILTO)
    message = fetch_json(url, 'api.crossref.org').get('message')
    if not message:
        return []
    locator, grade = classify_page(message.get('page'))
    issued = (message.get('issued') or {}).get('date-parts') or [[None]]
    authors = message.get('author') or []
    if not locator:
        locator, grade = '整篇（页码未收录）', 'article'
    return [{
        'kind': 'paper',
        'title': (message.get('title') or [''])[0],
        'year': issued[0][0],
        'id': message.get('DOI'),
        'venue': (message.get('container-title') or [None])[0],
        'locator': locator,
        'locator_grade': grade,
        'obtained': message.get('URL'),
        'pages': segment_reading_range(locator) if grade == 'page' else None,
        'authors': [' '.join(filter(None, (a.get('given'), a.get('family')))) for a in authors[:6]],
        'publisher': message.get('publisher'),
    }]


def search_classic(args):
    params = {
        'action': 'query', 'format': 'json', 'list': 'search',
        'srsearch': args.query, 'srlimit': str(args.limit),
    }
    payload = fetch_json(WS_API + urllib.parse.urlencode(params), 'zh.wikisource.org')
    hits = ((payload.get('query') or {}).get('search') or [])
    candidates = []
    for hit in hits:
        title = hit['title']
        volume = re.search(r'卷之[一二三四五六七八九十百零]+', title)
        locator = volume.group(0) if volume else title.split('/', 1)[-1]
        size = hit.get('size')
        grade = classic_grade(size)
        candidates.append({
            'kind': 'classic',
            'title': title,
            'id': 'zh.wikisource:' + title,
            'locator': locator,
            'locator_grade': grade,
            'obtained': 'https://zh.wikisource.org/wiki/' + urllib.parse.quote(title.replace(' ', '_')),
            'bytes': size,
            'approx_chars': round(size / 3) if size else None,
        })
    return candidates


def locate_classic(args):
    params = {
        'action': 'query', 'format': 'json', 'list': 'search',
        'srsearch': args.query, 'srlimit': str(args.limit), 'srnamespace': PAGE_NS,
    }
    payload = fetch_json(WS_API + urllib.parse.urlencode(params), 'zh.wikisource.org')
    hits = ((payload.get('query') or {}).get('search') or [])
    candidates = []
    for hit in hits:
        title = hit['title']
        parts = parse_page_title(title)
        candidates.append({
            'kind': 'classic',
            'title': title,
            'id': 'zh.wikisource:' + title,
            'edition': parts['edition'],
            'locator': ('第 %s 叶' % parts['leaf']) if parts['leaf'] else None,
            'locator_grade': 'leaf' if parts['leaf'] else 'none',
            'obtained': 'https://zh.wikisource.org/wiki/' + urllib.parse.quote(title.replace(' ', '_')),
            'volume_label': parts['volume_label'],
        })
    return candidates


def toc_classic(args):
    params = {'action': 'query', 'format': 'json', 'list': 'allpages',
              'apprefix': args.title + '/', 'aplimit': str(args.limit), 'apnamespace': '0'}
    payload = fetch_json(WS_API + urllib.parse.urlencode(params), 'zh.wikisource.org')
    pages = ((payload.get('query') or {}).get('allpages') or [])
    return [{
        'kind': 'toc',
        'title': page['title'],
        'id': 'zh.wikisource:' + page['title'],
        'locator': (re.search(r'卷之[一二三四五六七八九十百零]+', page['title']) or
                    re.match(r'.*', page['title'])).group(0),
        'locator_grade': 'volume',
        'obtained': 'https://zh.wikisource.org/wiki/' + urllib.parse.quote(page['title'].replace(' ', '_')),
    } for page in pages]


def zotero_headers():
    if not ZOTERO_KEY:
        raise SystemExit('缺少 ZOTERO_API_KEY 环境变量')
    return {'Zotero-API-Key': ZOTERO_KEY, 'Zotero-API-Version': '3'}


def zotero_base():
    if not ZOTERO_LIB:
        raise SystemExit('缺少 ZOTERO_LIBRARY_ID 环境变量')
    return 'https://api.zotero.org/users/%s' % ZOTERO_LIB


def zotero_check(args):
    payload = fetch_json(zotero_base() + '/items?limit=1',
                         'api.zotero.org', headers=zotero_headers())
    return [{'kind': 'zotero', 'status': 'ok', 'library': ZOTERO_LIB,
             'id': ZOTERO_LIB, 'locator': 'n/a', 'locator_grade': 'volume',
             'obtained': 'api.zotero.org', 'sample': bool(payload)}]


def zotero_find_doi(args):
    url = zotero_base() + '/items?q=' + urllib.parse.quote(args.doi) + '&qmode=everything&limit=5'
    payload = fetch_json(url, 'api.zotero.org', headers=zotero_headers())
    return [{
        'kind': 'zotero-item',
        'title': (item.get('data') or {}).get('title'),
        'id': (item.get('data') or {}).get('key'),
        'locator': (item.get('data') or {}).get('DOI'),
        'locator_grade': 'page',
        'obtained': 'zotero:%s' % ZOTERO_LIB,
        'match': args.doi.lower() in json.dumps(item).lower(),
    } for item in payload]


def selftest(args):
    checks = []

    def check(name, condition):
        checks.append((name, bool(condition)))

    check('openalex 页码范围', openalex_locator({'biblio': {'first_page': '138', 'last_page': '143'}})
          == ('页码 138-143', 'page'))
    check('openalex 无页码降级', openalex_locator({'biblio': {'volume': '41', 'issue': '1'}})
          == ('整篇（卷 41 第 1 期，页码未收录）', 'article'))
    check('openalex 空 biblio', openalex_locator({}) == (None, 'none'))
    check('阅读量估算 6 页', segment_reading_range('页码 138-143') == 6)
    check('阅读量估算 单页', segment_reading_range('页码 138') == 1)
    check('阅读量估算 空', segment_reading_range(None) is None)
    check('页码判定 区间', classify_page('138-143') == ('页码 138-143', 'page'))
    check('页码判定 单页', classify_page('138') == ('页码 138', 'page'))
    check('页码判定 文章号（含字母）',
          classify_page('e202318026') == ('整篇（文章号 e202318026）', 'article'))
    check('页码判定 文章号（长数字）',
          classify_page('9140057') == ('整篇（文章号 9140057）', 'article'))
    check('页码判定 空值', classify_page(None) == (None, None))

    papers = [
        {'title': 'good', 'id': '10.1/x', 'locator': '页码 1-9', 'locator_grade': 'page', 'obtained': 'u'},
        {'title': 'no-id', 'locator': '页码 1-9', 'locator_grade': 'page', 'obtained': 'u'},
        {'title': 'coarse', 'id': '10.1/y', 'locator': '卷 1', 'locator_grade': 'coarse', 'obtained': 'u'},
        {'title': 'article', 'id': '10.1/z', 'locator': '整篇（卷 9 第 1 期，页码未收录）',
         'locator_grade': 'article', 'obtained': 'u'},
    ]
    kept, dropped = gate(papers, 'paper')
    check('论文门禁：默认只留页码级', [c['title'] for c in kept] == ['good'])
    check('论文门禁：默认丢弃 3 条', len(dropped) == 3)
    kept, dropped = gate(papers, 'paper', allow_article=True)
    check('论文门禁：allow-article 放行整篇', [c['title'] for c in kept] == ['good', 'article'])
    check('论文门禁：allow-article 仍丢弃 coarse', len(dropped) == 2)

    classics = [
        {'title': '大明會典/卷之三十九 廩祿二', 'id': 'a', 'locator': '卷之三十九',
         'locator_grade': 'volume', 'obtained': 'u'},
        {'title': '无卷分页', 'id': 'b', 'locator': None, 'locator_grade': 'none', 'obtained': 'u'},
    ]
    kept, dropped = gate(classics, 'classic')
    check('古籍门禁：卷级可通过', [c['title'] for c in kept] == ['大明會典/卷之三十九 廩祿二'])
    check('古籍门禁：丢弃 1 条', len(dropped) == 1)

    check('wikisource API 无需鉴权即用', WS_API.startswith('https://zh.wikisource.org/w/api.php?'))
    check('页标题解析 哈佛藏本',
          parse_page_title('Page:Harvard drs 428230936 大明會典 v.61.pdf/2')
          == {'edition': '哈佛藏本', 'volume_label': 'v.61', 'leaf': '2'})
    gujin = parse_page_title('Page:Gujin Tushu Jicheng, Volume 704 (1700-1725).djvu/22')
    check('页标题解析 djvu 卷次', gujin['volume_label'] == 'Volume 704')
    check('页标题解析 djvu 叶次', gujin['leaf'] == '22')
    check('页标题解析 djvu 版本', gujin['edition'] == 'Gujin Tushu Jicheng')
    check('可读完原则 短篇通过', classic_grade(5000) == 'volume')
    check('可读完原则 长篇降级', classic_grade(50000) == 'coarse')
    check('可读完原则 体积未知降级', classic_grade(None) == 'coarse')

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print('%s %s' % ('PASS' if ok else 'FAIL', name))
    print('selftest: %d/%d' % (len(checks) - len(failed), len(checks)))
    return 1 if failed else 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog='retrieve.py', description='Canon Wright M1 检索入口')
    sub = parser.add_subparsers(dest='command', required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--out', help='结果写入文件（UTF-8）')

    p = sub.add_parser('search-paper', parents=[common], help='论文检索（OpenAlex，页码级）')
    p.add_argument('--query', required=True)
    p.add_argument('--lang', default='zh', help='语言过滤，传 all 表示不限')
    p.add_argument('--year-from')
    p.add_argument('--year-to')
    p.add_argument('--limit', type=int, default=8)
    p.add_argument('--allow-article', action='store_true',
                   help='接受「整篇」单元：期刊只给文章号、页码未收录时，整篇即阅读单元')
    p.set_defaults(handler=search_paper, gate_kind='paper')

    p = sub.add_parser('verify-doi', parents=[common], help='DOI 核验（Crossref）')
    p.add_argument('--doi', required=True)
    p.add_argument('--allow-article', action='store_true',
                   help='接受「整篇」单元：页码未收录时仍接受该文')
    p.set_defaults(handler=verify_doi, gate_kind='paper')

    p = sub.add_parser('search-classic', parents=[common], help='古籍全文检索（Wikisource）')
    p.add_argument('--query', required=True)
    p.add_argument('--limit', type=int, default=8)
    p.set_defaults(handler=search_classic, gate_kind='classic')

    p = sub.add_parser('locate-classic', parents=[common], help='古籍扫描叶定位（Wikisource Page 命名空间）')
    p.add_argument('--query', required=True)
    p.add_argument('--limit', type=int, default=5)
    p.set_defaults(handler=locate_classic, gate_kind='classic')

    p = sub.add_parser('toc-classic', parents=[common], help='古籍卷目录')
    p.add_argument('--title', required=True)
    p.add_argument('--limit', type=int, default=200)
    p.set_defaults(handler=toc_classic, gate_kind=None)

    p = sub.add_parser('zotero-check', parents=[common], help='校验 Zotero key 与连通性')
    p.set_defaults(handler=zotero_check, gate_kind=None)

    p = sub.add_parser('zotero-find-doi', parents=[common], help='在 Zotero 中查该 DOI 是否已入库')
    p.add_argument('--doi', required=True)
    p.set_defaults(handler=zotero_find_doi, gate_kind=None)

    p = sub.add_parser('selftest', parents=[common], help='离线自检，不联网')
    p.set_defaults(handler=selftest, gate_kind=None)

    args = parser.parse_args(argv)

    if args.handler is selftest:
        return selftest(args)

    result = args.handler(args)
    if args.gate_kind:
        result, _ = gate(result, args.gate_kind,
                         allow_article=getattr(args, 'allow_article', False))
    text = json.dumps(result, ensure_ascii=False, indent=2)

    if args.out:
        with open(args.out, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(text + '\n')
        print('wrote %d candidates to %s' % (len(result), args.out))
    else:
        sys.stdout.reconfigure(encoding='utf-8')
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
