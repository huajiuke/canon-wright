#!/usr/bin/env python3
'''卡片与暂存区的确定性操作。只用标准库。

为什么要有这个脚本：宪法第 2 节第 6 条要求「无归属不入库」加遗忘机制。
判断归属、计算库龄、超期归档都是确定性动作，不该交给模型逐次即兴决定——
否则同一张卡的命运会随提示词波动。

环境没有 PyYAML，这里实现一个严格的 YAML 子集解析器，只覆盖本项目的卡片与
config.yml 用到的写法：嵌套映射、内联列表、块标量、完整行注释、行尾注释。
解析不了就报错，绝不猜。
'''

import argparse
import datetime
import json
import pathlib
import re
import sys

REQUIRED_CARD_FIELDS = (
    ('id', 'id'),
    ('type', 'type'),
    ('segment', 'segment'),
    ('source.work', 'source.work'),
    ('source.locator.scheme', 'source.locator.scheme'),
    ('source.locator.edition', 'source.locator.edition'),
    ('source.locator.value', 'source.locator.value'),
    ('source.obtained', 'source.obtained'),
    ('status', 'status'),
    ('created', 'created'),
)

CARD_TYPES = ('fact', 'craft', 'motif')
CARD_STATUS = ('active', 'stale', 'archived')
FRONTMATTER = re.compile(r'^---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)', re.S)
INLINE_COMMENT = re.compile(r'\s+#')
STATUS_LINE = re.compile(r'(?m)^status:[ \t]*\S*[ \t]*$')


def _scalar(text):
    text = INLINE_COMMENT.split(text, maxsplit=1)[0].strip()
    if text.startswith('[') and text.endswith(']'):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [part.strip().strip("'") for part in inner.split(',') if part.strip()]
    if text in ('', '~', 'null'):
        return None
    return text.strip("'")


def _indent(line):
    return len(line) - len(line.lstrip(' '))


def _next_significant(lines, index):
    while index < len(lines) and not lines[index].strip():
        index += 1
    return index


def _parse_block(lines, index, indent):
    result = None
    index = _next_significant(lines, index)
    while index < len(lines):
        line = lines[index]
        current = _indent(line)
        if current < indent:
            break
        if current > indent:
            raise ValueError('第 %d 行缩进异常' % (index + 1))
        content = line.strip()
        if content.startswith('#'):
            index = _next_significant(lines, index + 1)
            continue
        if content.startswith('- '):
            if result is None:
                result = []
            if not isinstance(result, list):
                raise ValueError('第 %d 行列表与映射混用' % (index + 1))
            result.append(_scalar(content[2:]))
            index = _next_significant(lines, index + 1)
            continue
        if result is None:
            result = {}
        if not isinstance(result, dict):
            raise ValueError('第 %d 行映射与列表混用' % (index + 1))
        key, separator, value = content.partition(':')
        if not separator:
            raise ValueError('第 %d 行缺少冒号' % (index + 1))
        key = key.strip()
        value = value.strip()
        if value == '|':
            body = []
            cursor = index + 1
            while cursor < len(lines):
                raw = lines[cursor]
                if not raw.strip():
                    body.append('')
                    cursor += 1
                    continue
                if _indent(raw) <= indent:
                    break
                body.append(raw[indent + 2:] if len(raw) > indent + 2 else raw.strip())
                cursor += 1
            while body and not body[-1]:
                body.pop()
            result[key] = '\n'.join(body)
            index = _next_significant(lines, cursor)
            continue
        if value == '':
            cursor = _next_significant(lines, index + 1)
            if cursor < len(lines) and _indent(lines[cursor]) > indent:
                child, index = _parse_block(lines, cursor, _indent(lines[cursor]))
                result[key] = child
            else:
                result[key] = None
                index = cursor
            continue
        result[key] = _scalar(value)
        index = _next_significant(lines, index + 1)
    return result, index


def parse_yaml(text):
    lines = text.split('\n')
    start = _next_significant(lines, 0)
    if start >= len(lines):
        return {}
    value, _ = _parse_block(lines, start, _indent(lines[start]))
    return value if isinstance(value, dict) else {}


def read_card(path):
    text = pathlib.Path(path).read_text(encoding='utf-8')
    match = FRONTMATTER.match(text)
    if not match:
        raise ValueError('缺少 frontmatter（--- 包裹的头部）')
    return parse_yaml(match.group(1))


def dig(data, dotted):
    node = data
    for part in dotted.split('.'):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def has_belonging(data):
    belongs = data.get('belongs_to')
    if not isinstance(belongs, dict):
        return False
    for value in belongs.values():
        if isinstance(value, list):
            if value:
                return True
        elif value:
            return True
    return False


def validate_card(data, in_staging=False):
    problems = []
    for label, dotted in REQUIRED_CARD_FIELDS:
        value = dig(data, dotted)
        if isinstance(value, str):
            value = value.strip()
        if not value:
            problems.append('缺少 %s' % label)
    card_type = data.get('type')
    if card_type and card_type not in CARD_TYPES:
        problems.append('type 取值非法：%s' % card_type)
    status = data.get('status')
    if status and status not in CARD_STATUS:
        problems.append('status 取值非法：%s' % status)
    identifier = data.get('id')
    if identifier and not re.fullmatch(r'C-\d{8}-\d{3}', str(identifier)):
        problems.append('id 格式应为 C-YYYYMMDD-NNN：%s' % identifier)
    created = data.get('created')
    if created and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(created)):
        problems.append('created 格式应为 YYYY-MM-DD：%s' % created)
    if not has_belonging(data):
        if not in_staging:
            problems.append('belongs_to 为空，应进暂存区（无归属不入库）')
    elif in_staging:
        problems.append('已有归属，应移回 canon/cards/')
    return problems


def vault_root(start, explicit):
    if explicit:
        return pathlib.Path(explicit)
    current = pathlib.Path(start).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / '.canon' / 'config.yml').is_file():
            return candidate
    return None


def load_config(vault):
    path = pathlib.Path(vault) / '.canon' / 'config.yml'
    if not path.is_file():
        return {}
    return parse_yaml(path.read_text(encoding='utf-8'))


def card_files(directory, recursive=False):
    directory = pathlib.Path(directory)
    if not directory.is_dir():
        return []
    pattern = '**/*.md' if recursive else '*.md'
    return sorted(path for path in directory.glob(pattern)
                  if path.is_file() and not path.name.startswith('_'))


def next_card_id(directory, today):
    stamp = today.replace('-', '')
    highest = 0
    for path in card_files(directory):
        try:
            identifier = str(read_card(path).get('id') or '')
        except ValueError:
            continue
        match = re.fullmatch(r'C-(\d{8})-(\d{3})', identifier)
        if match and match.group(1) == stamp:
            highest = max(highest, int(match.group(2)))
    return 'C-%s-%03d' % (stamp, highest + 1)


def command_layout(args):
    vault = vault_root(pathlib.Path.cwd(), args.vault)
    if not vault:
        raise SystemExit('找不到 .canon/config.yml，请用 --vault 指定库根')
    config = load_config(vault)
    paths = config.get('paths') or {}
    rules = config.get('rules') or {}
    return {
        'vault': vault,
        'cards': vault / (paths.get('cards') or 'canon/cards'),
        'staging': vault / (paths.get('staging') or 'canon/staging'),
        'archive_days': int(rules.get('staging_archive_days') or 30),
    }


def command_check(args):
    layout = command_layout(args)
    results = []
    for directory, in_staging in ((layout['cards'], False), (layout['staging'], True)):
        for path in card_files(directory):
            try:
                problems = validate_card(read_card(path), in_staging=in_staging)
            except ValueError as error:
                problems = ['解析失败：%s' % error]
            results.append({'card': str(path.relative_to(layout['vault'])), 'problems': problems})
    bad = [item for item in results if item['problems']]
    for item in results:
        print('%s %s' % ('FAIL' if item['problems'] else 'OK  ', item['card']))
        for problem in item['problems']:
            print('       - %s' % problem)
    print('check: %d 张卡，%d 张有问题' % (len(results), len(bad)))
    return 1 if bad else 0


def command_new_id(args):
    layout = command_layout(args)
    today = args.date or datetime.date.today().isoformat()
    print(next_card_id(layout['cards'], today))
    return 0


def set_status(path, status):
    target = pathlib.Path(path)
    text = target.read_text(encoding='utf-8')
    updated, count = STATUS_LINE.subn('status: %s' % status, text, count=1)
    if count != 1:
        raise SystemExit('无法在 %s 中定位 status 字段' % path)
    target.write_text(updated, encoding='utf-8', newline='\n')


def command_staging(args):
    layout = command_layout(args)
    today = datetime.date.today()
    rows = []
    for path in card_files(layout['staging']):
        try:
            data = read_card(path)
        except ValueError as error:
            rows.append({'card': path.name, 'problem': str(error)})
            continue
        created = dig(data, 'created')
        age = None
        if created:
            try:
                age = (today - datetime.date.fromisoformat(str(created))).days
            except ValueError:
                age = None
        rows.append({
            'card': path.name,
            'id': data.get('id'),
            'status': data.get('status'),
            'created': created,
            'age_days': age,
            'days_left': (layout['archive_days'] - age) if age is not None else None,
        })
    print(json.dumps({'archive_days': layout['archive_days'], 'staging': rows},
                     ensure_ascii=False, indent=2))
    return 0


def command_sweep(args):
    layout = command_layout(args)
    vault_path = layout['vault'].resolve()
    today = datetime.date.today()
    actions = []

    def record(name, action, reason):
        actions.append({'card': name, 'action': action, 'reason': reason})

    for path in card_files(layout['cards']):
        try:
            data = read_card(path)
        except ValueError as error:
            record(path.name, 'skip', str(error))
            continue
        if has_belonging(data):
            continue
        destination = layout['staging'] / path.name
        if not path.resolve().is_relative_to(vault_path):
            raise SystemExit('拒绝移动：%s 不在库内' % path)
        if not destination.resolve().is_relative_to(vault_path):
            raise SystemExit('拒绝移动：%s 不在库内' % destination)
        if destination.exists():
            record(path.name, 'skip', '暂存区已有同名卡')
            continue
        record(path.name, 'to_staging', 'belongs_to 为空')
        if args.apply:
            layout['staging'].mkdir(parents=True, exist_ok=True)
            path.rename(destination)

    for path in card_files(layout['staging']):
        try:
            data = read_card(path)
        except ValueError as error:
            record(path.name, 'skip', str(error))
            continue
        if data.get('status') == 'archived':
            continue
        created = dig(data, 'created')
        try:
            age = (today - datetime.date.fromisoformat(str(created))).days
        except (ValueError, TypeError):
            record(path.name, 'skip', 'created 无法解析')
            continue
        if age <= layout['archive_days']:
            continue
        record(path.name, 'archive', '在暂存区已 %d 天，超过 %d 天' % (age, layout['archive_days']))
        if args.apply:
            set_status(path, 'archived')

    changed = [item for item in actions if item['action'] != 'skip']
    print(json.dumps({'mode': 'APPLIED' if args.apply else 'DRY-RUN',
                      'archive_days': layout['archive_days'], 'actions': actions},
                     ensure_ascii=False, indent=2))
    if not args.apply and changed:
        print('提示：加 --apply 才会真正移动与归档', file=sys.stderr)
    return 0


def command_selftest(args):
    checks = []

    def check(name, condition):
        checks.append((name, bool(condition)))

    nested = parse_yaml(
        'source:\n'
        '  work: 明史\n'
        '  locator:\n'
        '    scheme: 卷叶\n'
        '    edition: 中华书局点校本 1974\n'
        '    value: 卷八十一\n'
        'belongs_to:\n'
        '  entities: [沈砚, 铸剑坊]\n'
        'citations: []\n'
        'status: active   # active | stale | archived\n')
    check('嵌套映射', dig(nested, 'source.locator.edition') == '中华书局点校本 1974')
    check('三层取值', dig(nested, 'source.locator.value') == '卷八十一')
    check('内联列表', dig(nested, 'belongs_to.entities') == ['沈砚', '铸剑坊'])
    check('空列表', dig(nested, 'citations') == [])
    check('行尾注释剥离', nested.get('status') == 'active')
    check('整行注释跳过', parse_yaml('# 注释\nkey: v\n').get('key') == 'v')

    block = parse_yaml('segment: |\n  第一行\n\n  第三行\ntail: x\n')
    check('块标量保留空行', block.get('segment') == '第一行\n\n第三行')
    check('块标量后继续解析', block.get('tail') == 'x')

    valid = {
        'id': 'C-20260927-001', 'type': 'fact', 'segment': '原文',
        'source': {'work': '明史', 'obtained': '图书馆借阅',
                   'locator': {'scheme': '卷叶', 'edition': '中华书局', 'value': '卷八十一'}},
        'belongs_to': {'book': 'book-01'}, 'status': 'active', 'created': '2026-09-27',
    }
    check('合格卡无问题', validate_card(valid) == [])
    check('有归属判定', has_belonging(valid) is True)
    check('frontmatter 提取',
          FRONTMATTER.match('---\nid: C-1\n---\n正文').group(1) == 'id: C-1')

    def variant(mutate):
        clone = json.loads(json.dumps(valid))
        mutate(clone)
        return clone

    check('缺 edition 被拒',
          any('edition' in p for p in validate_card(
              variant(lambda c: c['source']['locator'].__setitem__('edition', '')))))
    check('缺原文片段被拒',
          any('segment' in p for p in validate_card(variant(lambda c: c.__setitem__('segment', '')))))
    check('缺 obtained 被拒',
          any('obtained' in p for p in validate_card(
              variant(lambda c: c['source'].__setitem__('obtained', None)))))

    orphan = variant(lambda c: c.__setitem__('belongs_to', {'entities': [], 'motif': None}))
    check('空 belongs_to 判为无归属', has_belonging(orphan) is False)
    check('无归属被拒并提示暂存区', any('暂存区' in p for p in validate_card(orphan)))
    check('暂存区内的无归属卡不再报错', validate_card(orphan, in_staging=True) == [])
    check('暂存区内已有归属则提示移回',
          any('移回' in p for p in validate_card(valid, in_staging=True)))
    check('cards 内有归属不提示移回',
          not any('移回' in p for p in validate_card(valid)))

    bad_type = variant(lambda c: c.__setitem__('type', 'story'))
    check('非法 type 被拒', any('type' in p for p in validate_card(bad_type)))
    bad_id = variant(lambda c: c.__setitem__('id', 'C-1'))
    check('非法 id 被拒', any('id' in p for p in validate_card(bad_id)))

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print('%s %s' % ('PASS' if ok else 'FAIL', name))
    print('selftest: %d/%d' % (len(checks) - len(failed), len(checks)))
    return 1 if failed else 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog='cards.py', description='卡片与暂存区操作')
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--vault', help='库根目录，默认向上查找 .canon/config.yml')
    sub = parser.add_subparsers(dest='command', required=True)

    p = sub.add_parser('check', parents=[common], help='校验卡片三要素、版本绑定与归属')
    p.set_defaults(handler=command_check)

    p = sub.add_parser('new-id', parents=[common], help='生成下一个卡片 id')
    p.add_argument('--date')
    p.set_defaults(handler=command_new_id)

    p = sub.add_parser('staging', parents=[common], help='列出暂存区卡片与剩余归档天数')
    p.set_defaults(handler=command_staging)

    p = sub.add_parser('sweep', parents=[common], help='无归属卡转入暂存区；超期卡归档（默认 dry-run）')
    p.add_argument('--apply', action='store_true', help='真正执行移动与归档')
    p.set_defaults(handler=command_sweep)

    p = sub.add_parser('selftest', parents=[common], help='离线自检，不读写库')
    p.set_defaults(handler=command_selftest)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == '__main__':
    raise SystemExit(main())
