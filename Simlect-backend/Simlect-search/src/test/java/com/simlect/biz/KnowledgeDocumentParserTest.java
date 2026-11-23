package com.simlect.biz;

import org.junit.jupiter.api.Test;
import org.apache.pdfbox.pdmodel.*;
import org.apache.pdfbox.pdmodel.font.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.zip.*;
import static org.junit.jupiter.api.Assertions.*;

class KnowledgeDocumentParserTest {
    KnowledgeDocumentParser parser=new KnowledgeDocumentParser();
    byte[] word(String xml)throws Exception {
        ByteArrayOutputStream out=new ByteArrayOutputStream();
        try(ZipOutputStream zip=new ZipOutputStream(out)){zip.putNextEntry(new ZipEntry("word/document.xml"));zip.write(xml.getBytes(StandardCharsets.UTF_8));zip.closeEntry();}
        return out.toByteArray();
    }
    @Test void txtRetainsChapterAndUnicode() {
        var parts=parser.parse("test.txt","# TEST ONLY\n不是正式政策。\n第二章 测试\n待人工审核".getBytes(StandardCharsets.UTF_8));
        assertEquals(2,parts.size());assertEquals("第二章 测试",parts.get(1).title());assertTrue(parts.get(1).text().contains("待人工审核"));
    }
    @Test void windowsEncodingAndBom() {
        assertTrue(parser.parse("test.txt","测试样例".getBytes(java.nio.charset.Charset.forName("GB18030"))).get(0).text().contains("测试样例"));
        assertEquals("TEST",parser.parse("test.txt","\ufeffTEST".getBytes(StandardCharsets.UTF_8)).get(0).text());
    }
    @Test void docxHeadingAndTableText()throws Exception {
        String xml="<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body><w:p><w:pPr><w:pStyle w:val='Heading1'/></w:pPr><w:r><w:t>TEST ONLY</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Not approved policy</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>";
        var sections=parser.parse("test.docx",word(xml));
        assertEquals("TEST ONLY",sections.get(0).title());assertTrue(sections.get(0).text().contains("Not approved policy"));
    }
    @Test void docxRejectsExternalEntities()throws Exception {
        assertThrows(RuntimeException.class,()->parser.parse("test.docx",word("<!DOCTYPE a [<!ENTITY x SYSTEM 'http://external.invalid/secret'>]><a>&x;</a>")));
    }
    @Test void pdfRetainsPage()throws Exception {
        ByteArrayOutputStream out=new ByteArrayOutputStream();
        try(PDDocument doc=new PDDocument()) {
            PDPage page=new PDPage();doc.addPage(page);
            try(PDPageContentStream c=new PDPageContentStream(doc,page)){c.beginText();c.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA),12);c.newLineAtOffset(30,700);c.showText("TEST ONLY NOT POLICY");c.endText();}
            doc.save(out);
        }
        var parts=parser.parse("test.pdf",out.toByteArray());assertEquals(1,parts.get(0).page());assertTrue(parts.get(0).text().contains("TEST ONLY"));
    }
    @Test void blankPdfRequiresOcr()throws Exception {
        ByteArrayOutputStream out=new ByteArrayOutputStream();try(PDDocument doc=new PDDocument()){doc.addPage(new PDPage());doc.save(out);}
        assertTrue(assertThrows(RuntimeException.class,()->parser.parse("scan.pdf",out.toByteArray())).getMessage().contains("OCR"));
    }
    @Test void splittingIsBoundedOverlappingAndVersioned() {
        String value="测试片段，非正式政策。".repeat(200);
        var parts=List.of(new KnowledgeDocumentParser.Section("测试章节",3,value));
        var chunks=parser.split("test",1,parts);
        assertTrue(chunks.size()>1);assertTrue(chunks.stream().allMatch(c->c.text().length()<=800 && c.page()==3 && c.section().equals("测试章节")));
        assertEquals(chunks.get(0).end()-120,chunks.get(1).start());
        assertNotEquals(chunks.get(0).chunkId(),parser.split("test",2,parts).get(0).chunkId());
        assertEquals(chunks.get(0).chunkId(),parser.split("test",1,parts).get(0).chunkId());
    }
    @Test void rejectsUnsupportedEmptyAndOversized() {
        assertThrows(RuntimeException.class,()->parser.parse("test.doc",new byte[]{1}));
        assertThrows(RuntimeException.class,()->parser.parse("test.txt",new byte[0]));
        assertThrows(RuntimeException.class,()->parser.parse("test.txt",new byte[10*1024*1024+1]));
    }
}
