"""Generate the reviewed native subtitle component for one user profile."""
from configuration import Profile
import json


def uses_learning_font(language):
    return language is not None and language not in ('en', 'zh-CN', 'zh-TW', 'ja')


def patch_configurable_source(source: str, profile: Profile, table=()) -> str:
    def replace_once(old, new):
        nonlocal source
        if source.count(old) != 1:
            raise ValueError('不支持的原生字幕组件结构：' + old[:70])
        source = source.replace(old, new)

    if 'MMShow' in source:
        raise ValueError('必须从原始字幕界面生成。')
    replace_once('   import flash.geom.ColorTransform;',
                 '   import flash.geom.ColorTransform;\n   import flash.filters.GlowFilter;')
    if any(uses_learning_font(code) for code in (profile.top_language, profile.bottom_language)):
        replace_once('   import flash.filters.GlowFilter;',
                     '   import flash.filters.GlowFilter;\n   import flash.text.Font;')
        replace_once('         super();', '         super();\n         Font.registerFont(MMLearningFontClass);')
        ending = source.rfind('\n}')
        if ending < 0:
            raise ValueError('字幕组件缺少包结束标记。')
        source = source[:ending] + '''
   public class MMLearningFontClass extends Font
   {
      public function MMLearningFontClass()
      {
         super();
      }
   }
''' + source[ending:]
    if profile.layout == 'stacked':
        replace_once('   import flash.geom.ColorTransform;',
                     '   import flash.geom.ColorTransform;\n   import flash.geom.Rectangle;')
    anchor = '      protected function ShowSubtitle(param1:MovieClip, param2:String, param3:Boolean, param4:uint, param5:Number) : void\n      {'
    replace_once(anchor, anchor + '''
         var mmTop:String = "";
         var mmStart:int = param2.indexOf("[[MMID:");
         var mmEnd:int = param2.indexOf("]]",mmStart + 7);
         var mmDual:Boolean = mmStart >= 0 && mmEnd >= mmStart + 7;
         this.mmDualSlots[param1 == this.subtitle_1 ? 0 : 1] = mmDual;
         if(mmDual)
         {
            var mmID:int = int(param2.substring(mmStart + 7,mmEnd));
            var mmPair:Array = this.MMReadLine(mmID);
            mmTop = String(mmPair[1]);
            param2 = param2.substring(0,mmStart) + String(mmPair[0]) + param2.substring(mmEnd + 2);
            param4 = this.TEXT_SIZE_NORMAL;
            param3 = MM_BOTTOM_BACKGROUND;
         }
'''.replace('MM_BOTTOM_BACKGROUND', str(profile.bottom_background).lower()))
    anchor = '         Environment.SetDefaultSubtitleStyleSheet(_loc7_);'
    replace_once(anchor, anchor + f'''
         if(mmDual)
         {{
            _loc7_.setStyle(".default",{{"color":Environment.GetSubtitleColorString(),"fontSize":{profile.bottom_size:g}{',"fontFamily":"MMLearningFont"' if uses_learning_font(profile.bottom_language) else ''}}});
            _loc6_.filters = {"[new GlowFilter(0,1,4,4,4,1)]" if profile.bottom_outline else "[]"};
         }}''')
    anchor = '         _loc6_.visible = true;\n      }'
    bottom = str(profile.bottom_language is not None).lower()
    replace_once(anchor, f'''         _loc6_.visible = !mmDual || {bottom};
         if(mmDual && !{bottom}) param1.bg.visible = false;
         this.MMShowTop(param1,mmTop);
      }}''')
    # Preserve the original parenting so fades, clears, pause and loads apply
    # even with the bottom text disabled. Never hide the owning MovieClip.
    snippet = '''      private function MMShowTop(owner:MovieClip, text:String) : void
      {
         var layer:MovieClip = owner.getChildByName("mmTop") as MovieClip;
         if(text.length == 0)
         {
            if(layer != null) layer.visible = false;
            this.MMPlaceTop();
            return;
         }
         if(layer == null)
         {
            layer = new subtitle_mc();
            layer.name = "mmTop";
            layer.mouseEnabled = layer.mouseChildren = false;
            owner.addChild(layer);
         }
         layer.alpha = 1;
         layer.visible = true;
         layer.message.big_txt.visible = false;
         layer.message.medium_txt.visible = false;
         var field:TextField = layer.message.txt;
         field.visible = true;
         field.autoSize = "center";
         field.wordWrap = true;
         field.multiline = true;
         field.filters = MM_TOP_FILTERS;
         var styles:StyleSheet = new StyleSheet();
         Environment.SetDefaultSubtitleStyleSheet(styles);
         styles.setStyle(".default",{"color":Environment.GetSubtitleColorString(),"fontSize":MM_TOP_SIZE MM_TOP_FONT});
         field.styleSheet = styles;
         ExternalInterface.call("addImageToTextField",field,"<span class='default'>" + text + "</span>");
         TextFieldEx.setVerticalAlign(field,"center");
         layer.bg.width = field.textWidth + 30;
         layer.bg.height = field.textHeight + 15;
         layer.bg.visible = MM_TOP_BACKGROUND;
         var tint:ColorTransform = new ColorTransform();
         tint.color = Environment.GetSubtitleBackgroundColor();
         layer.bg.transform.colorTransform = tint;
         this.MMPlaceTop();
      }

      private function MMPlaceTop() : void
      {
         var top:Number = MM_TOP_Y;
         var first:MovieClip = this.subtitle_1 == null ? null : this.subtitle_1.getChildByName("mmTop") as MovieClip;
         var second:MovieClip = this.subtitle_2 == null ? null : this.subtitle_2.getChildByName("mmTop") as MovieClip;
         if(first != null && first.visible && this.sub_1_show)
         {
            first.x = Environment.centerX - this.subtitle_1.x;
            first.y = top + first.bg.height / 2 - this.subtitle_1.y;
            top += first.bg.height + 15;
         }
         if(second != null && second.visible && this.sub_2_show)
         {
            second.x = Environment.centerX - this.subtitle_2.x;
            second.y = top + second.bg.height / 2 - this.subtitle_2.y;
         }
      }

'''
    if profile.layout == 'stacked':
        start = snippet.index('      private function MMPlaceTop()')
        snippet = snippet[:start] + """      private function MMPlaceTop() : void
      {
         this.MMPlaceStacked();
      }

      private function MMPlaceStacked() : void
      {
         var hasDual:Boolean = (this.sub_1_show && this.subtitle_1 != null && this.mmDualSlots[0] == true) || (this.sub_2_show && this.subtitle_2 != null && this.mmDualSlots[1] == true);
         if(!hasDual)
         {
            if(this.subtitle_1 != null) this.subtitle_1.y = this.sub_y;
            if(this.subtitle_2 != null)
            {
               this.subtitle_2.y = this.sub_y;
               if(this.sub_1_show && this.subtitle_1 != null)
                  this.subtitle_2.y = this.sub_y - this.subtitle_1.bg.height / 2 - this.subtitle_2.bg.height / 2 - 15;
            }
            return;
         }
         var cursor:Number = MM_BOTTOM_Y;
         var gap:Number = MM_LINE_GAP;
         var owners:Array = [this.subtitle_1,this.subtitle_2];
         var shown:Array = [this.sub_1_show,this.sub_2_show];
         var owner:MovieClip;
         var layer:MovieClip;
         var lowerField:TextField;
         var lowerBounds:Rectangle;
         var upperBounds:Rectangle;
         var lower:Boolean;
         var upper:Boolean;
         for(var i:int = 0; i < owners.length; i++)
         {
            owner = owners[i] as MovieClip;
            if(owner == null || !shown[i]) continue;
            lowerField = owner.message.txt;
            if(owner.message.big_txt.visible) lowerField = owner.message.big_txt;
            else if(owner.message.medium_txt.visible) lowerField = owner.message.medium_txt;
            layer = owner.getChildByName("mmTop") as MovieClip;
            lower = lowerField.visible && lowerField.text.length > 0;
            upper = this.mmDualSlots[i] == true && layer != null && layer.visible && layer.message.txt.text.length > 0;
            if(!lower && !upper) continue;
            if(lower)
            {
               lowerBounds = lowerField.getBounds(owner);
               owner.y = cursor - lowerBounds.bottom;
               cursor -= lowerBounds.height;
            }
            if(upper)
            {
               upperBounds = layer.message.txt.getBounds(layer);
               layer.x = 0;
               if(lower)
               {
                  cursor -= gap;
                  layer.y = cursor - upperBounds.bottom - owner.y;
               }
               else
               {
                  layer.y = 0;
                  owner.y = cursor - upperBounds.bottom;
               }
               cursor -= upperBounds.height;
            }
            cursor -= 15;
         }
      }

"""
        snippet = snippet.replace('MM_BOTTOM_Y', f'{profile.bottom_ui_y():.8g}')
        snippet = snippet.replace('MM_LINE_GAP', f'{profile.line_gap_px / profile.ui_scale():.8g}')
    for token, value in {
        'MM_TOP_Y': f'{profile.top_ui_y():.8g}',
        'MM_TOP_SIZE': f'{profile.top_size:g}',
        'MM_TOP_FILTERS': '[new GlowFilter(0,1,4,4,4,1)]' if profile.top_outline else '[]',
        'MM_TOP_BACKGROUND': str(profile.top_background).lower(),
        'MM_TOP_FONT': ',"fontFamily":"MMLearningFont"' if uses_learning_font(profile.top_language) else '',
    }.items():
        snippet = snippet.replace(token, value)
    anchor = '      public function FormatSubtitle(param1:MovieClip) : void'
    if profile.layout == 'stacked':
        # Insert in HideText before helper methods are inserted at FormatSubtitle.
        boundary = '      }\n      \n' + anchor
        replace_once(boundary, '         this.MMPlaceTop();\n' + boundary)
    data = '\x1e'.join(lower + '\x1f' + upper for lower, upper in table)
    dictionary = '''      private var mmDualSlots:Array = [false,false];

      private var mmLines:Array = null;

      private function MMReadLine(id:int) : Array
      {
         if(this.mmLines == null) this.mmLines = MM_DICTIONARY.split("\\u001e");
         if(id < 0 || id >= this.mmLines.length) return ["",""];
         return String(this.mmLines[id]).split("\\u001f");
      }

'''.replace('MM_DICTIONARY', json.dumps(data, ensure_ascii=True))
    replace_once(anchor, dictionary + snippet + anchor)
    anchor = '            this.subtitle_2.y = this.sub_y;\n         }\n      }'
    replace_once(anchor, '            this.subtitle_2.y = this.sub_y;\n         }\n         this.MMPlaceTop();\n      }')
    return source
