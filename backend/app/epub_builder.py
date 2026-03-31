import os
import ebooklib
from ebooklib import epub

class EpubBuilder:
    def __init__(self, title: str, author: str = "Unknown"):
        self.book = epub.EpubBook()
        
        self.book.set_identifier(f"id_{title.replace(' ', '_')}")
        self.book.set_title(title)
        self.book.set_language("vi")
        self.book.add_author(author)
        
        self.chapters = []

    def add_chapter(self, title: str, content: str, chapter_index: int):
        file_name = f"chapter_{chapter_index:04d}.xhtml"
        chapter = epub.EpubHtml(title=title, file_name=file_name, lang="vi")
        
        chapter.content = f"<h1>{title}</h1>\n{content}"
        
        self.book.add_item(chapter)
        self.chapters.append(chapter)

    def build(self, output_path: str) -> str:
        self.book.toc = tuple(self.chapters)
        self.book.spine = ['nav'] + self.chapters
        
        self.book.add_item(epub.EpubNcx())
        self.book.add_item(epub.EpubNav())
        
        epub.write_epub(output_path, self.book, {})
        return output_path