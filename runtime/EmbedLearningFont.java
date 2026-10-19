import com.jpexs.decompiler.flash.SWF;
import com.jpexs.decompiler.flash.tags.DefineFont3Tag;
import com.jpexs.decompiler.flash.tags.SymbolClassTag;
import com.jpexs.decompiler.flash.types.RECT;
import java.awt.Font;
import java.awt.font.FontRenderContext;
import java.awt.font.LineMetrics;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

/** Locally subset an OFL font into the generated GFX. Never changes source assets. */
public final class EmbedLearningFont {
    public static void main(String[] args) throws Exception {
        if (args.length != 6) throw new IllegalArgumentException("input.gfx output.gfx korean.ttf latin.ttf chinese.ttf characters.txt");
        SWF swf;
        try (InputStream input = Files.newInputStream(Path.of(args[0]))) { swf = new SWF(input, true); }
        Font source = Font.createFont(Font.TRUETYPE_FONT, Path.of(args[2]).toFile());
        Font latin = Font.createFont(Font.TRUETYPE_FONT, Path.of(args[3]).toFile());
        Font chinese = Font.createFont(Font.TRUETYPE_FONT, Path.of(args[4]).toFile());
        DefineFont3Tag font = new DefineFont3Tag(swf);
        font.fontName = "MMLearningFont";
        font.fontFlagsWideCodes = true;
        font.fontFlagsHasLayout = true;
        font.fontAdvanceTable = new ArrayList<>();
        font.fontBoundsTable = new ArrayList<RECT>();
        font.fontKerningTable = new ArrayList<>();
        LineMetrics metrics = source.deriveFont(20480f).getLineMetrics("Mg", new FontRenderContext(null,true,true));
        font.fontAscent = Math.min(65535, Math.round(metrics.getAscent()));
        font.fontDescent = Math.min(65535, Math.round(metrics.getDescent()));
        font.fontLeading = Math.round(metrics.getLeading());
        String characters = Files.readString(Path.of(args[5]), StandardCharsets.UTF_8);
        TreeSet<Character> unique = new TreeSet<>();
        for (char character : characters.toCharArray()) {
            if (character >= 32 && character != 127) unique.add(character);
        }
        swf.addTag(1, font);
        SymbolClassTag symbol = new SymbolClassTag(swf);
        symbol.tags.add(font.fontID);
        symbol.names.add("overlay.MMLearningFontClass");
        swf.addTag(2, symbol);
        for (char character : unique) {
            Font glyphSource = source.canDisplay(character) ? source : latin;
            if (!glyphSource.canDisplay(character)) glyphSource = chinese;
            if (!glyphSource.canDisplay(character)) throw new IOException("Font missing U+" + Integer.toHexString(character));
            if (!font.addCharacter(character, glyphSource)) throw new IOException("Cannot embed character");
        }
        try (OutputStream output = Files.newOutputStream(Path.of(args[1]))) { swf.saveTo(output); }
        System.out.println("Embedded MMLearningFont glyphs=" + unique.size());
    }
}
