"""Shared naming rules for AI record persistence."""


def build_ai_record_annotation_name(bag_filename, booklist_filename=None):
    return f"{bag_filename}+{booklist_filename or 'noBookList'}"
