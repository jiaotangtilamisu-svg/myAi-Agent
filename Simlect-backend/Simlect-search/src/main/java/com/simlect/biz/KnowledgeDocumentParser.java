package com.simlect.biz;

import com.simlect.exception.BusinessException;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.text.PDFTextStripper;
import org.springframework.stereotype.Component;
import org.w3c.dom.Element;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.charset.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.zip.ZipInputStream;

/** Bounded extraction only: never executes macros, follows links, or fetches external entities. */
@Component
public class KnowledgeDocumentParser {
    public record Section(String title, int page, String text) {}
    public record Chunk(String chunkId, int chunkIndex, String section, int page, int start, int end, String text, String sha256) {}
    private static final int MAX_BYTES=10*1024*1024, MAX_TEXT=400_000;
    public List<Section> parse(String filename, byte[] bytes) {
        if(bytes==null || bytes.length==0 || bytes.length>MAX_BYTES) throw new BusinessException("文档为空或超过10MiB");
        try {
            String lower=filename.toLowerCase(Locale.ROOT);
            List<Section> sections;
            if(lower.endsWith(".pdf")) {
                sections=new ArrayList<>();
                try(var pdf=Loader.loadPDF(bytes)) {
                    if(pdf.isEncrypted() || !pdf.getCurrentAccessPermission().canExtractContent()) throw new BusinessException("不支持加密或禁止提取的PDF");
                    if(pdf.getNumberOfPages()>200) throw new BusinessException("PDF超过200页");
                    PDFTextStripper reader=new PDFTextStripper();
                    for(int page=1;page<=pdf.getNumberOfPages();page++) {
                        reader.setStartPage(page);reader.setEndPage(page);
                        sections.addAll(sections(reader.getText(pdf),page));
                    }
                }
            } else if(lower.endsWith(".docx")) {
                byte[] xml=null; int total=0, entries=0;
                try(ZipInputStream zip=new ZipInputStream(new ByteArrayInputStream(bytes))) {
                    java.util.zip.ZipEntry entry;
                    while((entry=zip.getNextEntry())!=null) {
                        if(++entries>2000) throw new BusinessException("Word压缩包条目过多");
                        byte[] payload=zip.readNBytes(MAX_TEXT*8+1);
                        total+=payload.length;
                        if(payload.length>MAX_TEXT*8 || total>20*1024*1024) throw new BusinessException("Word解压大小超限");
                        if(entry.getName().equals("word/document.xml")) xml=payload;
                    }
                }
                if(xml==null) throw new BusinessException("无效DOCX文档");
                DocumentBuilderFactory factory=DocumentBuilderFactory.newInstance();
                factory.setNamespaceAware(true);
                factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl",true);
                factory.setFeature("http://xml.org/sax/features/external-general-entities",false);
                factory.setFeature("http://xml.org/sax/features/external-parameter-entities",false);
                factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD,"");factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA,"");
                var dom=factory.newDocumentBuilder().parse(new ByteArrayInputStream(xml));
                var paragraphs=dom.getElementsByTagNameNS("http://schemas.openxmlformats.org/wordprocessingml/2006/main","p");
                StringBuilder text=new StringBuilder();
                for(int i=0;i<paragraphs.getLength();i++) {
                    Element paragraph=(Element)paragraphs.item(i);
                    var styles=paragraph.getElementsByTagNameNS("http://schemas.openxmlformats.org/wordprocessingml/2006/main","pStyle");
                    if(styles.getLength()>0 && ((Element)styles.item(0)).getAttributeNS("http://schemas.openxmlformats.org/wordprocessingml/2006/main","val").matches("(?i)Heading.*|标题.*")) text.append("# ");
                    var runs=paragraph.getElementsByTagNameNS("http://schemas.openxmlformats.org/wordprocessingml/2006/main","t");
                    for(int j=0;j<runs.getLength();j++) text.append(runs.item(j).getTextContent());
                    text.append('\n');
                }
                sections=sections(text.toString(),0);
            } else if(lower.endsWith(".txt")) {
                String text;
                if(bytes.length>1 && (bytes[0]&255)==255 && (bytes[1]&255)==254) text=StandardCharsets.UTF_16LE.newDecoder().onMalformedInput(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes,2,bytes.length-2)).toString();
                else if(bytes.length>1 && (bytes[0]&255)==254 && (bytes[1]&255)==255) text=StandardCharsets.UTF_16BE.newDecoder().onMalformedInput(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes,2,bytes.length-2)).toString();
                else {
                    try {text=StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString();}
                    catch(CharacterCodingException e) {text=Charset.forName("GB18030").newDecoder().onMalformedInput(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString();}
                }
                sections=sections(text.replace("\ufeff",""),0);
            } else throw new BusinessException("仅支持PDF、DOCX、TXT；旧版DOC请先转换为DOCX");
            int length=sections.stream().mapToInt(s->s.text().length()).sum();
            if(length==0) throw new BusinessException("未提取到文本；扫描件需要先进行OCR");
            if(length>MAX_TEXT) throw new BusinessException("文档提取文本超过400000字符");
            return sections;
        }catch(BusinessException e){throw e;}catch(Exception e){throw new BusinessException("文档解析失败，请检查格式或编码",e);}
    }
    private List<Section> sections(String text,int page) {
        List<Section> out=new ArrayList<>();String title="正文";StringBuilder content=new StringBuilder();
        for(String line:text.replace("\r\n","\n").split("\n")) {
            String stripped=line.strip();
            if(stripped.matches("#{1,6}\\s+.+|第[一二三四五六七八九十百0-9]+[章节条].*")) {
                if(!content.toString().isBlank()) out.add(new Section(title,page,content.toString().strip()));
                title=stripped.replaceFirst("^#+\\s*","");content.setLength(0);
            }
            content.append(line).append('\n');
        }
        if(!content.toString().isBlank())out.add(new Section(title,page,content.toString().strip()));
        return out;
    }
    public List<Chunk> split(String id,long revision,List<Section> sections) {
        List<Chunk> chunks=new ArrayList<>();
        for(Section s:sections) {
            for(int start=0;start<s.text().length();) {
                int end=Math.min(start+800,s.text().length());
                if(end<s.text().length()) {
                    int boundary=Math.max(s.text().lastIndexOf('\n',end-1),s.text().lastIndexOf('。',end-1)+1);
                    if(boundary>start+400)end=boundary;
                    if(end>start && Character.isHighSurrogate(s.text().charAt(end-1)))end--;
                }
                String value=s.text().substring(start,end);
                int index=chunks.size();String chunkId=UUID.nameUUIDFromBytes(("simlect-policy:"+id+":"+revision+":"+index).getBytes(StandardCharsets.UTF_8)).toString();
                chunks.add(new Chunk(chunkId,index,s.title(),s.page(),start,end,value,hash(value)));
                if(chunks.size()>500)throw new BusinessException("文档超过500个分块，请拆分文档");
                if(end==s.text().length())break;
                start=end-120;
                if(start>0 && Character.isLowSurrogate(s.text().charAt(start)))start++;
            }
        }
        return chunks;
    }
    public static String hash(String value) {
        try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8)));}
        catch(Exception e){throw new IllegalStateException(e);}
    }
}
