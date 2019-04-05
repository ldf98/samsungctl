# -*- coding: utf-8 -*-
import wx
import os
import types
import keyword
import re
from wx.stc import *


FACES = {
    'times': 'Times New Roman',
    'mono':  'Courier New',
    'helv':  'Arial',
    'other': 'Comic Sans MS',
    'size':  10,
    'size2': 8,
}

if __file__:
    dir_name = os.path.dirname(__file__)
    if not dir_name:
        dir_name = os.getcwd()
else:
    dir_name = os.getcwd()

BASE_PATH = os.path.abspath(dir_name)


app = wx.App()


class DropTarget(wx.FileDropTarget):

    def __init__(self, parent):
        wx.FileDropTarget.__init__(self)
        self.parent = parent

    def OnDropFiles(self, x, y, names):
        self.parent.drop_files(names[0])
        return True


class FilePanel(wx.Panel):

    def __init__(self, parent):

        wx.Panel.__init__(self, parent, -1, style=wx.BORDER_NONE, size=(750, 175))

        self.line_ctrl = wx.StaticText(self, -1, 'Line: 0000')
        self.file_ctrl = wx.StaticText(self, -1, 'File: filename.py')
        self.func_ctrl = wx.StaticText(
            self,
            -1,
            'Function: some.function.name'
        )
        self.ctrl = PythonEditorCtrl(
            self,
            value='\n' * 5,
            style=wx.TE_MULTILINE | wx.TE_READONLY
        )

        sizer = wx.BoxSizer(wx.VERTICAL)
        top_sizer = wx.BoxSizer(wx.HORIZONTAL)
        top_sizer.Add(self.func_ctrl, 0, wx.EXPAND | wx.ALL, 5)
        top_sizer.Add(self.file_ctrl, 0, wx.EXPAND | wx.ALL, 5)
        top_sizer.Add(self.line_ctrl, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(top_sizer)
        sizer.Add(self.ctrl, 1, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(sizer)

    def SetFile(self, func_name, file_name, line_no):
        self.func_ctrl.SetLabel('Function: ' + str(func_name))
        self.line_ctrl.SetLabel('Line: ' + str(line_no))

        if file_name is None:
            self.file_ctrl.SetLabel('File: None')
            self.ctrl.SetValue('\n' * 5)
        else:

            file_name = 'samsungctl' + file_name.split('samsungctl')[-1]

            self.file_ctrl.SetLabel(
                'File: ' +
                file_name
            )

            self.ctrl.LoadFile(os.path.join(BASE_PATH, file_name))
            self.ctrl.GotoLine(int(line_no))

        self.Layout()


class Frame(wx.Frame):

    def __init__(self):
        wx.Frame.__init__(self, None, -1, size=(800, 1000))

        global records
        global record_number

        records = []
        record_number = 0

        next_button = wx.Button(self, -1, '>>', size=(30, 15))
        prev_button = wx.Button(self, -1, '<<', size=(30, 15))

        next_button.Enable(False)
        prev_button.Enable(False)

        time_ctrl = wx.StaticText(self, -1, '00:00:00')
        date_ctrl = wx.StaticText(self, -1, '00/00/00')
        thread_id_ctrl = wx.StaticText(self, -1, '0' * 10)
        thread_name_ctrl = wx.StaticText(self, -1, 'Thread Name')
        src_ctrl = FilePanel(self)
        dst_ctrl = FilePanel(self)
        out_ctrl = wx.TextCtrl(
            self,
            -1,
            '\n' * 5,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            size=(750, 175)
        )
        in_ctrl = wx.TextCtrl(
            self,
            -1,
            '\n' * 5,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            size=(750, 175)
        )

        thread_name_label = wx.StaticText(self, -1, 'Thread Name:')
        thread_id_label = wx.StaticText(self, -1, 'Thread Id:')
        date_label = wx.StaticText(self, -1, 'Date:')
        time_label = wx.StaticText(self, -1, 'Time:')

        def h_sizer(st, ctrl):
            temp_sizer = wx.BoxSizer(wx.HORIZONTAL)
            temp_sizer.Add(st, 0, wx.EXPAND | wx.ALL, 5)
            temp_sizer.Add(ctrl, 0, wx.EXPAND | wx.ALL, 5)
            return temp_sizer

        top_sizer = wx.BoxSizer(wx.HORIZONTAL)

        left_sizer = wx.BoxSizer(wx.VERTICAL)
        right_sizer = wx.BoxSizer(wx.VERTICAL)

        left_sizer.Add(h_sizer(date_label, date_ctrl))
        left_sizer.Add(h_sizer(time_label, time_ctrl))
        right_sizer.Add(h_sizer(thread_name_label, thread_name_ctrl))
        right_sizer.Add(h_sizer(thread_id_label, thread_id_ctrl))

        top_sizer.Add(left_sizer)
        top_sizer.Add(right_sizer)

        src_box = BoxedGroup(self, 'Source File', src_ctrl)
        dst_box = BoxedGroup(self, 'Destination File', dst_ctrl)
        out_box = BoxedGroup(self, 'Outgoing Data', out_ctrl)
        in_box = BoxedGroup(self, 'Incoming Data', in_ctrl)

        bottom_sizer = wx.BoxSizer(wx.HORIZONTAL)
        bottom_sizer.AddStretchSpacer(1)
        bottom_sizer.Add(prev_button)
        bottom_sizer.AddStretchSpacer(1)
        bottom_sizer.Add(next_button)
        bottom_sizer.AddStretchSpacer(1)

        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.Add(top_sizer)
        sizer.Add(src_box)
        sizer.Add(dst_box)
        sizer.Add(out_box)
        sizer.Add(in_box)
        sizer.Add(bottom_sizer)

        self.SetSizer(sizer)

        def change_record(increment):
            global record_number

            record_number += increment

            if record_number == len(records) - 1:
                next_button.Enable(False)
            else:
                next_button.Enable(True)

            if record_number == 0:
                prev_button.Enable(False)
            else:
                prev_button.Enable(True)

            (
                date,
                time,
                thread_name,
                thread_id,
                src,
                dst,
                msg,
                returned_data
            ) = records[record_number]

            src_func_name, src_file_data = src[5:].split(' [')
            src_file, src_line = src_file_data[:-1].split(':')
            src_ctrl.SetFile(src_func_name, src_file, src_line)

            date_ctrl.SetLabel(date)
            time_ctrl.SetLabel(time)
            thread_name_ctrl.SetLabel(thread_name)
            thread_id_ctrl.SetLabel(thread_id)

            if dst is not None:
                dst_func_name, dst_file_data = dst[5:].split(' [')
                dst_file, dst_line = dst_file_data[:-1].split(':')
                dst_ctrl.SetFile(dst_func_name, dst_file, dst_line)
            else:
                dst_ctrl.SetFile(None, None, None)

            if '<--' in msg:

                ip, msg = msg.split(' <-- ')
                try:
                    url, msg = msg.split(') ', 1)
                    url = url.split('(', 1)[-1]
                except ValueError:
                    msg, url = msg.split(': ', 1)

                msg = msg.replace('\\\\', '\\')

                if returned_data is not None:
                    returned_data = returned_data.split(')', 1)[-1].strip()
                    returned_data = returned_data.replace('\\\\', '\\')

                else:
                    returned_data = ''

                out_ctrl.SetValue(
                    'URL: ' + url + '\n' +
                    'DATA: \n' + msg
                )
                in_ctrl.SetValue(returned_data)

            elif '-->' in msg:
                ip, msg = msg.split(' --> ')
                ip = ip.replace("'", '')
                try:
                    url, msg = msg.split(') ', 1)
                    url = url.split('(', 1)[-1]
                except ValueError:
                    url = ip
                    msg = msg.replace("\\n'", "")

                msg = msg.replace('\\\\', '\\')
                returned_data = ''

                out_ctrl.SetValue(
                    'URL: ' + url + '\n' +
                    'DATA: \n' + msg
                )
                in_ctrl.SetValue(returned_data)

            elif '--' in msg:
                out_ctrl.SetValue(
                    'INFO: ' + msg + '\n'
                )
                in_ctrl.SetValue('')

            else:
                called_func, called_args = msg.split('(', 1)
                called_args = called_args.rsplit(')', 1)[0]

                args = []
                found_arg = ''

                for arg in called_args.split(', '):
                    if not arg.strip():
                        continue

                    if '=' not in arg:
                        found_arg += arg
                    else:
                        if found_arg:
                            args[len(args) - 1] += found_arg
                            found_arg = ''
                        args += [arg]

                called_args = ',\n'.join(args) + '\n'

                if returned_data is None:
                    returned_data = ''
                else:
                    result = []
                    returned_data = returned_data.split('=>')[-1].strip()

                    if (
                        returned_data.startswith('(') and
                        returned_data.endswith(')')
                    ):
                        brace_count = 0
                        found_arg = ''
                        for arg in returned_data[1:-1].split(', '):
                            if not arg.strip():
                                continue
                            brace_count += arg.count('(')
                            brace_count += arg.count('{')
                            brace_count += arg.count('[')
                            brace_count += arg.count('<')

                            brace_count -= arg.count(')')
                            brace_count -= arg.count('}')
                            brace_count -= arg.count(']')
                            brace_count -= arg.count('>')

                            if brace_count != 0:
                                found_arg += arg

                            else:
                                if found_arg:
                                    result += [found_arg + arg]
                                    found_arg = ''
                                else:
                                    result += [arg]

                        returned_data = ',\n'.join(result) + '\n'

                out_ctrl.SetValue(
                    'Called Function: ' + called_func + '\n' +
                    'Parameters: \n' + called_args
                )
                in_ctrl.SetValue(returned_data)

        def on_next(evt):
            wx.CallAfter(change_record, 1)
            evt.Skip()

        next_button.Bind(wx.EVT_BUTTON, on_next)

        def on_prev(evt):
            wx.CallAfter(change_record, -1)
            evt.Skip()

        prev_button.Bind(wx.EVT_BUTTON, on_prev)

        def on_drop(filepath):
            global records

            if not filepath.endswith('log'):
                return

            with open(filepath, 'r') as f:
                data = f.read()

            data = data.split('*[END]*\n')

            if len(data) == 1:
                return

            used_returns = []

            found_records = []

            def split_record(rec):
                rec = rec.split('*;*')[1:]
                dte, tme = rec[0].replace('  ', ' ').split(' ')
                t_name = rec[1]
                t_id = rec[2]
                sr = rec[3]
                mg = rec[4]

                if mg.startswith('dst:'):
                    dt = mg
                    mg = rec[5]
                else:
                    dt = None

                return dte, tme, t_name, t_id, sr, dt, mg

            for i, record in enumerate(data):
                if not record.startswith('DEBUG'):
                    continue

                if record in used_returns:
                    continue

                (
                    date,
                    time,
                    thread_name,
                    thread_id,
                    src,
                    dst,
                    msg
                ) = split_record(record)

                if src is None and dst is None:
                    continue

                if dst is None and '<--' in msg:
                    url = msg.split('(', 1)[-1].split(')', 1)[0]

                    for return_record in data[i:]:
                        if url in return_record and '-->' in return_record:
                            used_returns += [return_record]
                            returned_data = split_record(return_record)[-1:]
                            break
                    else:
                        returned_data = None

                elif dst is not None:
                    for return_record in data[i:]:
                        if (
                            '=>' in return_record and
                            src in return_record and
                            dst in return_record
                        ):
                            used_returns += [return_record]
                            returned_data = split_record(return_record)[-1:]
                            break
                    else:
                        returned_data = None

                else:
                    returned_data = None

                found_records += [
                    [
                        date,
                        time,
                        thread_name,
                        thread_id,
                        src,
                        dst,
                        msg,
                        returned_data
                    ]
                ]

            if found_records:
                del records[:]
                records = found_records[:]
                change_record(-record_number)

        self.drop_files = on_drop

        filedroptarget = DropTarget(self)
        self.SetDropTarget(filedroptarget)


class PythonEditorCtrl(StyledTextCtrl):
    def __init__(
        self,
        parent,
        pos=wx.DefaultPosition,
        size=wx.DefaultSize,
        style=0,
        value="",
    ):
        StyledTextCtrl.__init__(self, parent, -1, pos, size, style)
        self.SetCodePage(STC_CP_UTF8)
        StyleSetSpec = self.StyleSetSpec  # IGNORE:C0103

        self.CmdKeyAssign(ord('B'), STC_SCMOD_CTRL, STC_CMD_ZOOMIN)
        self.CmdKeyAssign(ord('N'), STC_SCMOD_CTRL, STC_CMD_ZOOMOUT)

        # Setup a margin to hold fold markers
        # self.SetFoldFlags(16)  # WHAT IS THIS VALUE?

        self.Bind(EVT_STC_UPDATEUI, self.OnUpdateUI)
        self.Bind(EVT_STC_MARGINCLICK, self.OnMarginClick)
        # Make some styles,  The lexer defines what each style is used for, we
        # just have to define what each style looks like.  This set is adapted
        # from Scintilla sample property files.

        # Global default styles for all languages
        StyleSetSpec(STC_STYLE_DEFAULT, "face:%(helv)s,size:%(size)d" % FACES)
        self.StyleClearAll()  # Reset all to be like the default

        # Global default styles for all languages
        StyleSetSpec(STC_STYLE_DEFAULT, "face:%(helv)s,size:%(size)d" % FACES)
        StyleSetSpec(STC_STYLE_CONTROLCHAR, "face:%(other)s" % FACES)

        # Python styles
        # End of line where string is not closed
        StyleSetSpec(
            STC_P_STRINGEOL,
            "fore:#000000,face:%(mono)s,back:#E0C0E0,eol,size:%(size)d" % FACES
        )

        # register some images for use in the AutoComplete box.
        # self.RegisterImage(1, images.getSmilesBitmap())
        # self.RegisterImage(2, images.getFile1Bitmap())
        # self.RegisterImage(3, images.getCopy2Bitmap())

        self.SetLexer(STC_LEX_PYTHON)
        self.SetKeyWords(0, " ".join(keyword.kwlist))

        # Enable folding
        self.SetProperty("fold", "1")

        # Highlight tab/space mixing (shouldn't be any)
        self.SetProperty("tab.timmy.whinge.level", "1")

        # Set left and right margins
        self.SetMargins(2, 2)

        # Set up the numbers in the margin for margin #1
        self.SetMarginType(1, STC_MARGIN_NUMBER)
        # Reasonable value for, say, 4-5 digits using a mono font (40 pix)
        self.SetMarginWidth(1, 40)

        # Indentation and tab stuff
        self.SetIndentSize(value)
        self.SetIndentationGuides(True)  # Show indent guides
        self.SetBackSpaceUnIndents(True)  # Backspace unindents rather than
        # delete 1 space
        self.SetTabIndents(True)  # Tab key indents
        self.SetUseTabs(False)  # Use spaces rather than tabs, or
        # TabTimmy will complain!
        # White space
        self.SetViewWhiteSpace(False)  # Don't view white space

        # EOL: Since we are loading/saving ourselves, and the
        # strings will always have \n's in them, set the STC to
        # edit them that way.
        self.SetEOLMode(STC_EOL_LF)
        self.SetViewEOL(False)

        # No right-edge mode indicator
        self.SetEdgeMode(STC_EDGE_NONE)

        # Setup a margin to hold fold markers
        self.SetMarginType(2, STC_MARGIN_SYMBOL)
        self.SetMarginMask(2, STC_MASK_FOLDERS)
        self.SetMarginSensitive(2, True)
        self.SetMarginWidth(2, 12)

        # and now set up the fold markers
        MarkerDefine = self.MarkerDefine  # IGNORE:C0103
        MarkerDefine(
            STC_MARKNUM_FOLDEREND, STC_MARK_BOXPLUSCONNECTED, "white", "black"
        )
        MarkerDefine(
            STC_MARKNUM_FOLDEROPENMID,
            STC_MARK_BOXMINUSCONNECTED,
            "white",
            "black"
        )
        MarkerDefine(
            STC_MARKNUM_FOLDERMIDTAIL, STC_MARK_TCORNER, "white", "black"
        )
        MarkerDefine(
            STC_MARKNUM_FOLDERTAIL, STC_MARK_LCORNER, "white", "black"
        )
        MarkerDefine(
            STC_MARKNUM_FOLDERSUB, STC_MARK_VLINE, "white", "black"
        )
        MarkerDefine(
            STC_MARKNUM_FOLDER, STC_MARK_BOXPLUS, "white", "black"
        )
        MarkerDefine(
            STC_MARKNUM_FOLDEROPEN, STC_MARK_BOXMINUS, "white", "black"
        )

        # Global default style
        StyleSetSpec(
            STC_STYLE_DEFAULT,
            'fore:#000000,back:#FFFFFF,face:Courier New,size:9'
        )

        # Clear styles and revert to default.
        self.StyleClearAll()

        # Following style specs only indicate differences from default.
        # The rest remains unchanged.

        # Line numbers in margin
        StyleSetSpec(STC_STYLE_LINENUMBER, 'fore:#000000,back:#99A9C2')
        # Highlighted brace
        StyleSetSpec(STC_STYLE_BRACELIGHT, 'fore:#00009D,back:#FFFF00')
        # Unmatched brace
        StyleSetSpec(STC_STYLE_BRACEBAD, 'fore:#00009D,back:#FF0000')
        # Indentation guide
        StyleSetSpec(STC_STYLE_INDENTGUIDE, "fore:#CDCDCD")

        # Python styles
        StyleSetSpec(STC_P_DEFAULT, 'fore:#000000')
        # Comments
        StyleSetSpec(STC_P_COMMENTLINE, 'fore:#008000')
        StyleSetSpec(STC_P_COMMENTBLOCK, 'fore:#008000')
        # Numbers
        StyleSetSpec(STC_P_NUMBER, 'fore:#008080')
        # Strings and characters
        StyleSetSpec(STC_P_STRING, 'fore:#800080')
        StyleSetSpec(STC_P_CHARACTER, 'fore:#800080')
        # Keywords
        StyleSetSpec(STC_P_WORD, 'fore:#000080,bold')
        # Triple quotes
        # StyleSetSpec(STC_P_TRIPLE, 'fore:#800080,back:#FFFFEA')
        # StyleSetSpec(STC_P_TRIPLEDOUBLE, 'fore:#800080,back:#FFFFEA')
        StyleSetSpec(STC_P_TRIPLE, 'fore:#808000')
        StyleSetSpec(STC_P_TRIPLEDOUBLE, 'fore:#808000')
        # Class names
        StyleSetSpec(STC_P_CLASSNAME, 'fore:#0000FF,bold')
        # Function names
        StyleSetSpec(STC_P_DEFNAME, 'fore:#008080,bold')
        # Operators
        StyleSetSpec(STC_P_OPERATOR, 'fore:#800000,bold')
        # Identifiers. I leave this as not bold because everything seems
        # to be an identifier if it doesn't match the above criteria
        StyleSetSpec(STC_P_IDENTIFIER, 'fore:#000000')

        # Caret color
        self.SetCaretForeground("BLUE")
        # Selection background
        self.SetSelBackground(1, '#66CCFF')

        self.SetSelBackground(
            True,
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)
        )
        self.SetSelForeground(
            True,
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHTTEXT)
        )
        self.UsePopUp(False)

        # Keyword Search/Context Sensitive Autoindent.
        self.rekeyword = re.compile(
            r"(\sreturn\b)|(\sbreak\b)|(\spass\b)|(\scontinue\b)|(\sraise\b)",
            re.MULTILINE
        )
        self.reslash = re.compile(r"\\\Z")
        self.renonwhitespace = re.compile('\S', re.M)

        # popup menu
        menu = wx.Menu()

        def AddMenuItem(ident, menuId):
            self.Bind(wx.EVT_MENU, getattr(self, "OnCmd" + ident), id=menuId)
            return menu.Append(menuId, ident)

        AddMenuItem("Copy", wx.ID_COPY)
        menu.AppendSeparator()
        AddMenuItem("SelectAll", wx.ID_SELECTALL)
        self.popupMenu = menu

        self.Bind(wx.EVT_RIGHT_UP, self.OnRightClick)

        self.SetText(value)
        self.EmptyUndoBuffer()
        self.Bind(EVT_STC_SAVEPOINTLEFT, self.OnSavePointLeft)

    def AutoIndent(self):
        indentSize = self.SetIndentSize(self.GetValue())

        pos = self.GetCurrentPos()

        # Strip trailing whitespace first.
        currentline = self.LineFromPosition(pos)
        lineendpos = self.GetLineEndPosition(currentline)
        if lineendpos > pos:
            self.SetTargetStart(pos)
            self.SetTargetEnd(lineendpos)
            textRange = self.GetTextRange(pos, lineendpos)
            self.ReplaceTarget(textRange.rstrip())

        # Look at last line
        pos = pos - 1
        clinenumber = self.LineFromPosition(pos)

        linenumber = clinenumber

        self.GotoPos(pos)

        self.GotoLine(clinenumber)

        numtabs = self.GetLineIndentation(clinenumber + 1) / indentSize

        search = self.renonwhitespace.search
        if (
            search(self.GetLine(clinenumber + 1)) is not None and
            search(self.GetLine(clinenumber)) is None
        ):
            numtabs += self.GetLineIndentation(clinenumber) / indentSize

        if numtabs == 0:
            numtabs = self.GetLineIndentation(linenumber) / indentSize

        if True:
            checkat = self.GetLineEndPosition(linenumber) - 1
            if self.GetCharAt(checkat) == ord(':'):
                numtabs = numtabs + 1
            else:
                lastline = self.GetLine(linenumber)
                # Remove Comment:
                comment = lastline.find('#')
                if comment > -1:
                    lastline = lastline[:comment]
                if self.reslash.search(lastline.rstrip()) is None:
                    if self.rekeyword.search(lastline) is not None:
                        numtabs = numtabs - 1
        # Go to current line to add tabs

        self.SetTargetStart(pos + 1)
        end = self.GetLineEndPosition(clinenumber + 1)
        self.SetTargetEnd(end)

        self.ReplaceTarget(self.GetTextRange(pos + 1, end).lstrip())

        pos = pos + 1
        self.GotoPos(pos)
        x = 0
        while (x < numtabs):
            self.AddText(' ' * indentSize)
            x = x + 1
        # /Auto Indent Code

        # Ensure proper keyboard navigation:
        self.CmdKeyExecute(STC_CMD_CHARLEFT)
        self.CmdKeyExecute(STC_CMD_CHARRIGHT)

    def Expand(self, line, doExpand, force=False, visLevels=0, level=-1):
        lastChild = self.GetLastChild(line, level)
        line = line + 1

        while line <= lastChild:
            if force:
                if visLevels > 0:
                    self.ShowLines(line, line)
                else:
                    self.HideLines(line, line)
            else:
                if doExpand:
                    self.ShowLines(line, line)

            if level == -1:
                level = self.GetFoldLevel(line)

            if level & STC_FOLDLEVELHEADERFLAG:
                if force:
                    self.SetFoldExpanded(line, visLevels > 1)
                    line = self.Expand(line, doExpand, force, visLevels - 1)
                else:
                    flag = doExpand and self.GetFoldExpanded(line)
                    line = self.Expand(line, flag, force, visLevels - 1)
            else:
                line = line + 1

        return line

    def FoldAll(self):
        lineCount = self.GetLineCount()
        expanding = True

        # find out if we are folding or unfolding
        for lineNum in range(lineCount):
            if self.GetFoldLevel(lineNum) & STC_FOLDLEVELHEADERFLAG:
                expanding = not self.GetFoldExpanded(lineNum)
                break

        lineNum = 0

        while lineNum < lineCount:
            level = self.GetFoldLevel(lineNum)
            if (
                level & STC_FOLDLEVELHEADERFLAG and
                (level & STC_FOLDLEVELNUMBERMASK) == STC_FOLDLEVELBASE
            ):
                if expanding:
                    self.SetFoldExpanded(lineNum, True)
                    lineNum = self.Expand(lineNum, True)
                    lineNum = lineNum - 1
                else:
                    lastChild = self.GetLastChild(lineNum, -1)
                    self.SetFoldExpanded(lineNum, False)

                    if lastChild > lineNum:
                        self.HideLines(lineNum + 1, lastChild)

            lineNum = lineNum + 1

    def GetValue(self):
        return self.GetText()

    def OnCmdCopy(self, dummyEvent=None):
        self.Copy()

    def OnCmdSelectAll(self, dummyEvent=None):
        self.SelectAll()

    def OnMarginClick(self, event):
        # fold and unfold as needed
        if event.GetMargin() == 2:
            if event.GetShift() and event.GetControl():
                self.FoldAll()
            else:
                lineClicked = self.LineFromPosition(event.GetPosition())

                if self.GetFoldLevel(lineClicked) & STC_FOLDLEVELHEADERFLAG:
                    if event.GetShift():
                        self.SetFoldExpanded(lineClicked, True)
                        self.Expand(lineClicked, True, True, 1)
                    elif event.GetControl():
                        if self.GetFoldExpanded(lineClicked):
                            self.SetFoldExpanded(lineClicked, False)
                            self.Expand(lineClicked, False, True, 0)
                        else:
                            self.SetFoldExpanded(lineClicked, True)
                            self.Expand(lineClicked, True, True, 100)
                    else:
                        self.ToggleFold(lineClicked)

    def OnModified(self, event):
        event.Skip()

    def OnRightClick(self, dummyEvent):
        menu = self.popupMenu
        first, last = self.GetSelection()
        menu.Enable(wx.ID_UNDO, self.CanUndo())
        menu.Enable(wx.ID_REDO, self.CanUndo())
        menu.Enable(wx.ID_CUT, first != last)
        menu.Enable(wx.ID_COPY, first != last)
        menu.Enable(wx.ID_PASTE, self.CanPaste())
        menu.Enable(wx.ID_DELETE, first != last)
        menu.Enable(wx.ID_SELECTALL, True)
        self.PopupMenu(menu)

    def OnSavePointLeft(self, event):
        self.Bind(EVT_STC_MODIFIED, self.OnModified)
        event.Skip()

    def OnUpdateUI(self, dummyEvent):
        # check for matching braces
        braceAtCaret = -1
        braceOpposite = -1
        charBefore = None
        caretPos = self.GetCurrentPos()

        if caretPos > 0:
            charBefore = self.GetCharAt(caretPos - 1)
            styleBefore = self.GetStyleAt(caretPos - 1)

        # check before
        if (
            charBefore and
            chr(charBefore) in "[]{}()" and
            styleBefore == STC_P_OPERATOR
        ):
            braceAtCaret = caretPos - 1

        # check after
        if braceAtCaret < 0:
            charAfter = self.GetCharAt(caretPos)
            styleAfter = self.GetStyleAt(caretPos)
            if (
                charAfter and
                chr(charAfter) in "[]{}()" and
                styleAfter == STC_P_OPERATOR
            ):
                braceAtCaret = caretPos

        if braceAtCaret >= 0:
            braceOpposite = self.BraceMatch(braceAtCaret)

        if braceAtCaret != -1 and braceOpposite == -1:
            self.BraceBadLight(braceAtCaret)
        else:
            self.BraceHighlight(braceAtCaret, braceOpposite)
            # pt = self.PointFromPosition(braceOpposite)
            # self.Refresh(True, wxRect(pt.x, pt.y, 5,5))
            # self.Refresh(False)

    def SetIndentSize(self, value):
        indentSize = 4
        if value:
            match = re.search("^( +)", value, re.MULTILINE)
            if match:
                indentSize = len(match.group())
        self.SetIndent(indentSize)
        self.SetTabWidth(indentSize)
        return indentSize

    def SetValue(self, value):
        self.SetText(value)


class BoxedGroup(wx.StaticBoxSizer):
    def __init__(self, parent, label="", *items):
        staticBox = wx.StaticBox(parent, -1, label)
        wx.StaticBoxSizer.__init__(self, staticBox, wx.VERTICAL)
        self.items = []
        for item in items:
            lineSizer = wx.BoxSizer(wx.HORIZONTAL)
            if isinstance(item, types.StringTypes):
                labelCtrl = wx.StaticText(parent, -1, item)
                lineSizer.Add(
                    labelCtrl,
                    0,
                    wx.LEFT | wx.ALIGN_CENTER_VERTICAL,
                    5
                )
                self.items.append([labelCtrl])
            elif isinstance(item, (types.ListType, types.TupleType)):
                lineItems = []
                for subitem in item:
                    if isinstance(subitem, types.StringTypes):
                        subitem = wx.StaticText(parent, -1, subitem)
                        lineSizer.Add(
                            subitem,
                            0,
                            wx.LEFT | wx.ALIGN_CENTER_VERTICAL,
                            5
                        )
                    else:
                        lineSizer.Add(
                            subitem,
                            0,
                            wx.ALL | wx.ALIGN_CENTER_VERTICAL,
                            5
                        )
                    lineItems.append(subitem)
                self.items.append(lineItems)
            else:
                lineSizer.Add(item, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
                self.items.append([item])
            self.Add(lineSizer, 1, wx.EXPAND)

    def AppendItem(self):
        pass

    def GetColumnItems(self, colNum):
        return [row[colNum] for row in self.items if len(row) > colNum]


log_frame = Frame()
log_frame.Show()
app.MainLoop()
