"""Export an explicitly selected local book to the public demonstration bundle."""
import argparse
import json
from pathlib import Path
from coursebook_agent.models import CourseBook
from coursebook_agent.renderer.presentation import reader_projection
from coursebook_agent.renderer.markdown import render_coursebook


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--book', type=Path, required=True)
    args = parser.parse_args()
    original = CourseBook.model_validate(json.loads(args.book.read_text()))
    if str(original.course.course_id) != '74397':
        parser.error('This demo manifest is for course 74397 only; prepare a matching manifest for another book.')
    book = CourseBook.model_validate(reader_projection(original.model_dump()))
    resources = [
        {'title': '课堂资料一 · 随机现象与事件', 'summary': '介绍随机试验、样本空间、事件关系及概率公理，建立用集合语言表示概率问题的基础。', 'topics': ['随机试验', '样本空间', '事件运算', '概率公理']},
        {'title': '课堂资料二 · 概率模型与条件推理', 'summary': '从古典概型与计数方法进入条件概率，通过完整例题讨论全概率公式和贝叶斯公式。', 'topics': ['古典概型', '条件概率', '全概率', '贝叶斯公式']},
        {'title': '课堂资料三 · 独立性与离散分布', 'summary': '讨论事件独立性与随机变量，将事件计算推广到二项分布、泊松分布及其应用。', 'topics': ['事件独立性', '随机变量', '二项分布', '泊松分布']},
    ]
    target = Path('frontend/public/demo-assets')
    target.mkdir(parents=True, exist_ok=True)
    data = {'book': book.model_dump(), 'resources': resources, 'generated_at': '2026-10-09'}
    # No raw resources, account settings, events or credentials enter the bundle.
    (target / 'demo.json').write_text(json.dumps(data, ensure_ascii=False))
    (target / 'coursebook.md').write_text(render_coursebook(book))
    print(f'Exported {len(book.chapters)} chapters to {target}')


if __name__ == '__main__':
    main()
