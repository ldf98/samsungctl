import os
import sys
import wx
import threading
from wx import richtext
# from wx import aui
from wx.lib.agw import aui
from slider_ctrl import SliderCtrl

app = wx.App()


class RemoteUpdate(threading.Thread):

    def __init__(self):
        self._event = threading.Event()
        self._update_callbacks = []
        threading.Thread.__init__(self)

    def register_callback(self, callback):
        self._update_callbacks += [callback]

    def run(self):
        while not self._event.isSet():
            for callback in self._update_callbacks:
                callback()
                if self._event.isSet():
                    break

            self._event.wait(10.0)

    def stop(self):
        self._event.set()
        self.join(2.0)


remote_update = RemoteUpdate()


class StdOut(object):

    def __init__(self, std, ctrl):
        self._std = std
        self._ctrl = ctrl

    def __getattr__(self, item):
        if item in self.__dict__:
            return self.__dict__[item]

        return getattr(self._std, item)

    def write(self, data):
        self._std.write(data)
        def do():
            self._ctrl.BeginTextColour((255, 255, 255))
            self._ctrl.WriteText(data)
            self._ctrl.EndTextColour()

        wx.CallAfter(do)


class StdErr(object):

    def __init__(self, std, ctrl):
        self._std = std
        self._ctrl = ctrl

    def __getattr__(self, item):
        if item in self.__dict__:
            return self.__dict__[item]

        return getattr(self._std, item)

    def write(self, data):
        self._std.write(data)
        def do():
            self._ctrl.BeginTextColour((255, 0, 0))
            self._ctrl.WriteText(data)
            self._ctrl.EndTextColour()

        wx.CallAfter(do)


class LogPane(wx.Panel):

    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1, style=wx.BORDER_SUNKEN)
        sizer = wx.BoxSizer(wx.VERTICAL)

        ctrl = self.ctrl = wx.richtext.RichTextCtrl(
            self,
            -1,
            '',
            style=(
                richtext.RE_MULTILINE |
                richtext.RE_READONLY
            )
        )

        sizer.Add(ctrl, 1, wx.EXPAND | wx.ALL, 10)

        ctrl.SetBackgroundColour(wx.BLACK)
        ctrl.SetForegroundColour(wx.WHITE)

        self.SetSizer(sizer)

        sys.stdout = StdOut(sys.stdout, ctrl)
        sys.stderr = StdErr(sys.stderr, ctrl)


class ChoicePanel(wx.Panel):

    def __init__(self, handler, parent, name, choices):
        wx.Panel.__init__(self, parent, -1, style=wx.BORDER_NONE)

        ctrl = wx.Choice(self, -1, choices=choices)
        label = wx.StaticText(self, -1, name + ':')

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(label, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(ctrl, 1, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(sizer)

        ctrl.SetSelection(0)

        def on_choice(_):
            handler.ControlChange()

        ctrl.Bind(wx.EVT_CHOICE, on_choice)

        def get_value():
            return ctrl.GetStringSelection()

        def set_value(value):
            if value in choices:
                ctrl.SetStringSelection(value)
            else:
                ctrl.SetSelection(0)

        self.GetValue = get_value
        self.SetValue = set_value


class SliderPanel(wx.Panel):

    def __init__(self, handler, parent, name, min_val, max_val, step):
        wx.Panel.__init__(self, parent, -1, style=wx.BORDER_NONE)

        val = (max_val - min_val) / 2
        if step is None:
            step = 0

        ctrl = SliderCtrl(
            self,
            -1,
            value=val,
            minValue=min_val,
            maxValue=max_val,
            increment=step,
            size=(100, 50),
            style=(
                wx.SL_HORIZONTAL |
                wx.SL_AUTOTICKS |
                wx.SL_LABELS |
                wx.SL_BOTTOM
            )
        )

        label = wx.StaticText(self, -1, name)
        label_sizer = wx.BoxSizer(wx.HORIZONTAL)

        label_sizer.AddStretchSpacer(1)
        label_sizer.Add(label, 0, wx.EXPAND)
        label_sizer.AddStretchSpacer(1)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(label_sizer, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(ctrl, 1, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(sizer)

        def on_slide(_):
            handler.ControlChange()

        ctrl.Bind(wx.EVT_SCROLL_CHANGED, on_slide)

        def get_value():
            return ctrl.GetValue()

        def set_value(value):
            ctrl.Unbind(wx.EVT_SCROLL_CHANGED, handler=on_slide)
            ctrl.SetValue(value)
            ctrl.Bind(wx.EVT_SCROLL_CHANGED, on_slide)

        self.GetValue = get_value
        self.SetValue = set_value


class BoolPanel(wx.Panel):

    def __init__(self, handler, parent, name):
        wx.Panel.__init__(self, parent, -1, style=wx.BORDER_NONE)

        ctrl = wx.CheckBox(self, -1, '')
        label = wx.StaticText(self, -1, name + ':')

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(label, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(ctrl, 1, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(sizer)

        def on_check(_):
            handler.ControlChange()

        ctrl.Bind(wx.EVT_CHECKBOX, on_check)

        def get_value():
            return ctrl.GetValue()

        def set_value(value):
            ctrl.SetValue(value)

        self.GetValue = get_value
        self.SetValue = set_value


class StringPanel(wx.Panel):

    def __init__(self, handler, parent, name):
        wx.Panel.__init__(self, parent, -1, style = wx.BORDER_NONE)

        ctrl = wx.TextCtrl(self, -1, ' ' * 20)
        label = wx.StaticText(self, -1, name + ':')

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(label, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(ctrl, 1, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(sizer)

        def on_char(evt):
            key_code = evt.GetKeyCode()
            if key_code == wx.WXK_RETURN:
                handler.ControlChange()
            else:
                evt.Skip()

        ctrl.Bind(wx.EVT_CHAR_HOOK, on_char)

        def get_value():
            return ctrl.GetValue()

        def set_value(value):
            ctrl.SetValue(value)

        self.GetValue = get_value
        self.SetValue = set_value

        def enable_control():
            ctrl.Enable(True)

        def disable_control():
            ctrl.Enable(False)

        self.EnableControl = enable_control
        self.DisableControl = disable_control


class Method(wx.StaticBoxSizer):
    def __init__(self, parent, label, method):
        self.method = method
        static_box = wx.StaticBox(parent, -1, label)
        wx.StaticBoxSizer.__init__(self, static_box, wx.VERTICAL)

        ctrl_sizer = wx.BoxSizer(wx.HORIZONTAL)

        params = method.params
        ctrls = []

        for param in params:
            name = param.__name__
            if name.lower() == 'instanceid':
                continue
            default_value = param.default_value
            if param.py_data_type[0] == str:
                allowed_values = param.allowed_values
                if allowed_values is not None:
                    ctrl = ChoicePanel(self, parent, name, allowed_values)
                else:
                    ctrl = StringPanel(self, parent, name)

            elif param.py_data_type[0] == bool:
                ctrl = BoolPanel(self, parent, name)

            elif param.py_data_type[0] in (float, int):
                ctrl = SliderPanel(
                    self,
                    parent,
                    name,
                    min_val=param.minimum,
                    max_val=param.maximum,
                    step=param.step
                )
            else:
                continue

            if default_value is not None:
                ctrl.SetValue(default_value)

            ctrls += [ctrl]

        self.ctrls = ctrls

        left_sizer = wx.BoxSizer(wx.VERTICAL)
        right_sizer = wx.BoxSizer(wx.VERTICAL)
        count = 0

        for ctrl in ctrls:
            if count:
                right_sizer.Add(ctrl)
                count -= 1
            else:
                left_sizer.Add(ctrl)
                count += 1

        self.button = wx.Button(parent, -1, 'SEND', size=(30, 20))
        self.button.Bind(wx.EVT_BUTTON, self.on_button)
        self.button.Enable(False)

        output_ctrl = self.output_ctrl = wx.richtext.RichTextCtrl(
            parent,
            -1,
            '',
            style=(
                richtext.RE_MULTILINE |
                richtext.RE_READONLY
            )
        )

        output_ctrl.SetBackgroundColour(wx.BLACK)
        output_ctrl.SetForegroundColour(wx.WHITE)
        output_ctrl.BeginTextColour((255, 255, 255))

        right_sizer.Add(self.button, 0, wx.ALL | wx.ALIGN_RIGHT, 5)
        ctrl_sizer.Add(left_sizer, 0, wx.EXPAND)
        ctrl_sizer.Add(right_sizer, 0, wx.EXPAND)

        self.Add(ctrl_sizer)
        self.Add(output_ctrl, 1, wx.EXPAND | wx.ALL, 10)

    def EnableControls(self):
        for ctrl in self.ctrls:
            ctrl.EnableControl()

    def DisableControls(self):
        for ctrl in self.ctrls:
            ctrl.DisableControl()

    def ControlChange(self):
        self.button.Enable(True)

    def on_button(self, _):
        values = []
        offset = 0
        for i, param in enumerate(self.method.params):
            name = param.__name__
            if name.lower() == 'instanceid':
                value = 0
                offset -= 1
            else:
                ctrl = self.ctrls[i + offset]
                value = ctrl.GetValue()

            values += [value]

        response = self.method(*values)

        for i, ret_val in enumerate(self.method.ret_vals):
            name = ret_val.__name__
            self.output_ctrl.WriteText(name + ': ' + str(response[i]))

        self.button.Enable(False)


class GetSetMethod(wx.StaticBoxSizer):
    def __init__(self, parent, label, getter, setter):
        self.getter = getter
        self.setter = setter
        static_box = wx.StaticBox(parent, -1, label)
        wx.StaticBoxSizer.__init__(self, static_box, wx.HORIZONTAL)

        setter_params = setter.params
        setter_ctrls = []

        for param in setter_params:
            name = param.__name__
            if name.lower() == 'instanceid':
                continue
            default_value = param.default_value
            if param.py_data_type[0] == str:
                allowed_values = param.allowed_values
                if allowed_values is not None:
                    ctrl = ChoicePanel(self, parent, name, allowed_values)
                else:
                    ctrl = StringPanel(self, parent, name)

            elif param.py_data_type[0] == bool:
                ctrl = BoolPanel(self, parent, name)

            elif param.py_data_type[0] in (float, int):
                ctrl = SliderPanel(
                    self,
                    parent,
                    name,
                    min_val=param.minimum,
                    max_val=param.maximum,
                    step=param.step
                )
            else:
                continue

            if default_value is not None:
                ctrl.SetValue(default_value)

            setter_ctrls += [ctrl]

        self.setter_ctrls = setter_ctrls

        remote_update.register_callback(self)

        left_sizer = wx.BoxSizer(wx.VERTICAL)
        right_sizer = wx.BoxSizer(wx.VERTICAL)
        count = 0

        for ctrl in setter_ctrls:
            if count:
                right_sizer.Add(ctrl)
                count -= 1
            else:
                left_sizer.Add(ctrl)
                count += 1

        self.Add(left_sizer, 0, wx.EXPAND)
        self.Add(right_sizer, 0, wx.EXPAND)

    def __call__(self):
        values = []
        offset = 0
        for i, getter_param in enumerate(self.getter.params):
            getter_param_name = getter_param.__name__
            if getter_param_name.lower() == 'instanceid':
                value = 0
                offset -= 1
            else:
                setter_ctrl = self.setter_ctrls[i + offset]
                value = setter_ctrl.GetValue()

            values += [value]

        ret_vals = self.getter(*values)
        offset = 0

        for i, ret_val in enumerate(self.getter.ret_vals):
            if ret_val.__name__ == 'Result':
                offset -= 1
                continue

            setter_ctrl = self.setter_ctrls[i + offset]
            value = ret_vals[i]
            setter_ctrl.SetValue(value)

    def EnableControls(self):
        for ctrl in self.setter_ctrls:
            ctrl.EnableControl()

    def DisableControls(self):
        for ctrl in self.setter_ctrls:
            ctrl.DisableControl()

    def ControlChange(self):
        values = []
        offset = 0
        for i, param in enumerate(self.setter.params):
            name = param.__name__
            if name.lower() == 'instanceid':
                value = 0
                offset -= 1
            else:
                ctrl = self.setter_ctrls[i + offset]
                value = ctrl.GetValue()

            values += [value]

        response = self.setter(*values)
        result = []

        for i, ret_val in enumerate(self.setter.ret_vals):
            name = ret_val.__name__
            result += [dict(value_name=name, value=response[i])]
        return result


class ServicePanel(wx.Panel):

    def __init__(self, parent, service, methods):
        wx.Panel.__init__(self, parent, -1, style=wx.BORDER_NONE)

        method_dict = {}
        pairs = []

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        left_sizer = wx.BoxSizer(wx.VERTICAL)
        middle_sizer = wx.BoxSizer(wx.VERTICAL)
        right_sizer = wx.BoxSizer(wx.VERTICAL)

        count = 0

        for method in methods:
            name = method['name']
            method = getattr(service, name)

            if name.startswith('X_'):
                name = name[2:]

            if name.startswith('Get'):
                partner_name = name.replace('Get', 'Set')
                if partner_name in method_dict:
                    pairs += [name[3:]]

            elif name.startswith('Set'):
                partner_name = name.replace('Set', 'Get')
                if partner_name in method_dict:
                    pairs += [name[3:]]

            method_dict[name] = method

            done_methods = []

            for method_name in pairs:
                done_methods += ['Get' + method_name, 'Set' + method_name]
                getter = method_dict['Get' + method_name]
                setter = method_dict['Set' + method_name]

                box_sizer = GetSetMethod(self, method_name, getter, setter)

                if count == 1:
                    middle_sizer.Add(box_sizer, 0, wx.ALL, 5)
                    count += 1
                elif count == 2:
                    right_sizer.Add(box_sizer, 0, wx.ALL, 5)
                    count = 0
                else:
                    left_sizer.Add(box_sizer, 0, wx.ALL, 5)
                    count += 1

        sizer.Add(left_sizer)
        sizer.Add(middle_sizer)
        sizer.Add(right_sizer)

        self.SetSizer(sizer)


class BoxedGroup(wx.StaticBoxSizer):
    def __init__(self, parent, label="", direction=wx.VERTICAL, *items):
        static_box = wx.StaticBox(parent, -1, label)
        wx.StaticBoxSizer.__init__(self, static_box, direction)

        for text, ctrl in items:
            label_ctrl = wx.StaticText(parent, -1, text)
            if isinstance(ctrl, SliderCtrl):
                line_sizer = wx.BoxSizer(wx.VERTICAL)
                if text:
                    label_sizer = wx.BoxSizer(wx.HORIZONTAL)
                    label_sizer.AddStretchSpacer(1)
                    label_sizer.Add(label_ctrl, 0, wx.EXPAND | wx.ALL, 5)
                    label_sizer.AddStretchSpacer(1)
                    line_sizer.Add(label_sizer)

            else:
                line_sizer = wx.BoxSizer(wx.HORIZONTAL)
                line_sizer.Add(
                    label_ctrl,
                    0,
                    wx.LEFT | wx.ALIGN_CENTER_VERTICAL,
                    5
                )

            line_sizer.Add(ctrl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
            self.Add(line_sizer, 0, wx.EXPAND)


class TVMainPage(wx.Panel):

    def __init__(self, parent, remote):
        self._remote = remote
        wx.Panel.__init__(self, parent, -1, style=wx.BORDER_NONE)

        from samsungctl.key_mappings import KEY_MAPPINGS

        key_choices = []

        for _, keys in KEY_MAPPINGS:
            key_choices += list(key for _, key in keys)

        def get_slider_ctrl():
            ctrl = SliderCtrl(
                self,
                -1,
                value=0,
                minValue=0,
                maxValue=100,
                increment=1,
                size=(300, 75),
                style=(
                    wx.SL_HORIZONTAL |
                    wx.SL_AUTOTICKS |
                    wx.SL_LABELS |
                    wx.SL_BOTTOM
                )
            )
            ctrl.SetBackgroundColour(self.GetBackgroundColour())
            return ctrl

        brightness_ctrl = get_slider_ctrl()
        sharpness_ctrl = get_slider_ctrl()
        contrast_ctrl = get_slider_ctrl()
        color_ctrl = get_slider_ctrl()
        aspect_ctrl = wx.Choice(self, -1, choices=[])

        def on_brightness(_):
            value = brightness_ctrl.GetValue()
            remote.brightness = value

        brightness_ctrl.Bind(wx.EVT_SLIDER, on_brightness)

        def on_sharpness(_):
            value = sharpness_ctrl.GetValue()
            remote.sharpness = value

        sharpness_ctrl.Bind(wx.EVT_SLIDER, on_sharpness)

        def on_contrast(_):
            value = contrast_ctrl.GetValue()
            remote.contrast = value

        contrast_ctrl.Bind(wx.EVT_SLIDER, on_contrast)

        def on_color(_):
            value = color_ctrl.GetValue()
            remote.volume = value

        color_ctrl.Bind(wx.EVT_SLIDER, on_color)

        def on_aspect(_):
            value = aspect_ctrl.GetStringSelection()
            remote.volume = value

        aspect_ctrl.Bind(wx.EVT_CHOICE, on_aspect)

        volume_ctrl = get_slider_ctrl()
        mute_ctrl = wx.CheckBox(self, -1, '')

        def on_volume(_):
            value = volume_ctrl.GetValue()
            remote.volume = value

        volume_ctrl.Bind(wx.EVT_SLIDER, on_volume)

        def on_mute(_):
            value = mute_ctrl.GetValue()
            remote.mute = value

        mute_ctrl.Bind(wx.EVT_CHECKBOX, on_mute)

        keycode_ctrl = wx.Choice(self, -1, choices=key_choices)
        voice_ctrl = wx.CheckBox(self, -1, '')
        text_ctrl = wx.TextCtrl(self, -1, '')
        text_ctrl.Enable(remote.config.method == 'websocket')

        def on_text(evt):
            key_code = evt.GetKeyCode()
            if key_code == wx.WXK_RETURN:
                value = text_ctrl.GetValue()
                remote.input_text(value)
            else:
                evt.Skip()

        text_ctrl.Bind(wx.EVT_CHAR_HOOK, on_text)

        voice_ctrl.Enable(remote.config.method == 'websocket')

        def on_voice(_):
            value = voice_ctrl.GetValue()
            if value:
                remote.start_voice_recognition()
            else:
                remote.stop_voice_recognition()

        voice_ctrl.Bind(wx.EVT_CHECKBOX, on_voice)

        def on_keycode(_):
            value = keycode_ctrl.GetStringSelection()
            remote.command(value)

        keycode_ctrl.Bind(wx.EVT_CHOICE, on_keycode)

        source_ctrl = wx.Choice(self, -1, choices=[])
        source_name_ctrl = wx.StaticText(self, -1, ' ' * 20)
        source_label_ctrl = wx.TextCtrl(self, -1, ' ' * 20)
        source_device_ctrl = wx.StaticText(self, -1, ' ' * 20)
        source_type_ctrl = wx.StaticText(self, -1, ' ' * 20)
        source_brand_ctrl = wx.StaticText(self, -1, ' ' * 20)
        source_model_ctrl = wx.StaticText(self, -1, ' ' * 20)
        source_active_ctrl = wx.StaticText(self, -1, ' ' * 20)
        source_connected_ctrl = wx.StaticText(self, -1, ' ' * 20)
        source_viewable_ctrl = wx.StaticText(self, -1, ' ' * 20)
        source_button = wx.Button(self, -1, 'Select', size=(40, 30))

        def on_source(_):
            label = source_ctrl.GetStringSelection()
            for source in remote.sources:
                if source.label == label:
                    source_ctrl.SetStringSelection(source.label)
                    source_name_ctrl.SetLabel(source.name)
                    source_label_ctrl.SetValue(source.label)
                    if source.is_editable:
                        source_label_ctrl.Enable(True)
                    else:
                        source_label_ctrl.Enable(False)

                    device = source.attached_device
                    if device is not None:
                        source_type_ctrl.SetLabel(device.device_type)
                        source_brand_ctrl.SetLabel(device.brand)
                        source_model_ctrl.SetLabel(device.model)
                    else:
                        source_type_ctrl.SetLabel('')
                        source_brand_ctrl.SetLabel('')
                        source_model_ctrl.SetLabel('')

                    source_device_ctrl.SetLabel(source.device_name)
                    source_active_ctrl.SetLabel(str(source.is_active))
                    source_connected_ctrl.SetLabel(str(source.is_connected))
                    source_viewable_ctrl.SetLabel(str(source.is_viewable))
                    break

        source_ctrl.Bind(wx.EVT_CHOICE, on_source)

        def on_label(evt):
            key_code = evt.GetKeyCode()
            if key_code == wx.WXK_RETURN:
                name = source_name_ctrl.GetLabel()
                for source in remote.sources:
                    if source.name == name:
                        source.label = source_label_ctrl.GetValue()
                        break
            else:
                evt.Skip()

        source_label_ctrl.Bind(wx.EVT_CHAR_HOOK, on_label)

        def on_source_button(_):
            sources = remote.sources
            label = source_ctrl.GetStringSelection()
            for source in sources:
                if source.label == label:
                    source.activate()
                    break

        source_button.Bind(wx.EVT_BUTTON, on_source_button)

        source_button.Enable(remote.source is not None)

        volume_box = BoxedGroup(
            self,
            'Volume Controls',
            wx.VERTICAL,
            ('Mute:', mute_ctrl),
            ('', BoxedGroup(self, 'Volume', wx.VERTICAL, ('', volume_ctrl))),
        )
        source_box = BoxedGroup(
            self,
            'Source Controls',
            wx.VERTICAL,
            ('Source:', source_ctrl),
            ('Name:', source_name_ctrl),
            ('Label:', source_label_ctrl),
            ('Device Name:', source_device_ctrl),
            ('Device Type:', source_type_ctrl),
            ('Device Brand:', source_brand_ctrl),
            ('Device Model:', source_model_ctrl),
            ('Active:', source_active_ctrl),
            ('Connected:', source_connected_ctrl),
            ('Viewable:', source_viewable_ctrl),
            ('', source_button)
        )
        image_box = BoxedGroup(
            self,
            'Image Controls',
            wx.HORIZONTAL,
            ('', BoxedGroup(self, 'Brightness', wx.VERTICAL, ('', brightness_ctrl))),
            ('', BoxedGroup(self, 'Sharpness', wx.VERTICAL, ('', sharpness_ctrl))),
            ('', BoxedGroup(self, 'Contrast', wx.VERTICAL, ('', contrast_ctrl))),
            ('', BoxedGroup(self, 'Color Temperature', wx.VERTICAL, ('', color_ctrl))),
            ('Aspect Ratio:', aspect_ctrl)
        )

        misc_box = BoxedGroup(
            self,
            'Misc Controls',
            wx.VERTICAL,
            ('Remote Keys:', keycode_ctrl),
            ('Voice Recognition:', voice_ctrl),
            ('Send Text:', text_ctrl),
        )

        sizer = wx.GridBagSizer(3, 2)

        sizer.Add(source_box, (0, 0), (2, 1))
        sizer.Add(volume_box, (0, 1), (1, 1))
        sizer.Add(misc_box, (1, 1), (1, 1))
        sizer.Add(image_box, (2, 0), (1, 2))

        self.SetSizer(sizer)

        def update():
            brightness = remote.brightness
            contrast = remote.contrast
            sharpness = remote.sharpness
            color_temperature = remote.color_temperature
            volume = remote.volume
            mute = remote.mute
            source = remote.source

            if source is None:
                source_label = ''
                source_name = ''
                source_editable = ''
                device_name = ''
                device_type = ''
                device_brand = ''
                device_model = ''
                source_active = ''
                source_connected = ''
                source_viewable = ''
            else:
                source_label = source.label
                source_name = source.name
                source_editable = source.is_editable
                device_name = source.device_name

                attached_device = source.attached_device
                if attached_device is None:
                    device_type = ''
                    device_brand = ''
                    device_model = ''
                else:
                    device_type = attached_device.device_type
                    device_brand = attached_device.brand
                    device_model = attached_device.model

                source_active = source.is_active
                source_connected = source.is_connected
                source_viewable = source.is_viewable

            sources = remote.sources
            if sources is None:
                source_choices = []
            else:
                source_choices = list(source.label for source in sources)

            try:
                obj = remote.RenderingControl.X_SetAspectRatio

                for param in obj.params:
                    if param.__name__ == 'AspectRatio':
                        aspect_choices = param.allowed_values[:]
                        break
                else:
                    aspect_choices = []
            except AttributeError:
                aspect_choices = []

            aspect_ratio = remote.aspect_ratio

            def do():

                if brightness is None:
                    brightness_ctrl.Enable(False)
                else:
                    brightness_ctrl.SetValue(brightness)

                if contrast is None:
                    contrast_ctrl.Enable(False)
                else:
                    contrast_ctrl.Enable(True)
                    contrast_ctrl.SetValue(contrast)

                if sharpness is None:
                    sharpness_ctrl.Enable(False)
                else:
                    sharpness_ctrl.Enable(True)
                    sharpness_ctrl.SetValue(sharpness)

                if color_temperature is None:
                    color_ctrl.Enable(False)
                else:
                    color_ctrl.Enable(True)
                    color_ctrl.SetValue(color_temperature)

                if aspect_ctrl.GetStrings() != aspect_choices:
                    value = aspect_ctrl.GetStringSelection()
                    aspect_ctrl.Clear()
                    aspect_ctrl.AppendItems(aspect_choices)
                    if aspect_choices:
                        aspect_ctrl.SetStringSelection(value)

                if aspect_ratio is None:
                    aspect_ctrl.Enable(False)
                else:
                    aspect_ctrl.Enable(True)
                    aspect_ctrl.SetStringSelection(aspect_ratio)

                if volume is None:
                    volume_ctrl.Enable(False)
                else:
                    volume_ctrl.Enable(True)
                    volume_ctrl.SetValue(volume)

                if mute is None:
                    mute_ctrl.Enable(False)
                else:
                    mute_ctrl.Enable(True)
                    mute_ctrl.SetValue(mute)

                if source_ctrl.GetStrings() != source_choices:
                    value = source_ctrl.GetStringSelection()
                    source_ctrl.Clear()
                    source_ctrl.AppendItems(source_choices)
                    if source_choices:
                        source_ctrl.SetStringSelection(value)

                if source is None:
                    source_ctrl.Enable(False)
                    source_label_ctrl.Enable(False)
                    source_button.Enable(False)
                else:
                    source_ctrl.Enable(True)
                    source_label_ctrl.Enable(True)
                    source_button.Enable(True)
                    source_ctrl.SetStringSelection(source_label)
                    source_name_ctrl.SetLabel(source_name)
                    source_label_ctrl.SetValue(source_label)
                    if not source_editable:
                        source_label_ctrl.Enable(False)

                    source_type_ctrl.SetLabel(device_type)
                    source_brand_ctrl.SetLabel(device_brand)
                    source_model_ctrl.SetLabel(device_model)

                    source_device_ctrl.SetLabel(device_name if device_name else '')
                    source_active_ctrl.SetLabel(str(source_active))
                    source_connected_ctrl.SetLabel(str(source_connected))
                    source_viewable_ctrl.SetLabel(str(source_viewable))

            do()

        update()

        remote_update.register_callback(update)


class TVPane(wx.Notebook):

    def __init__(self, parent, remote):
        self._remote = remote

        wx.Notebook.__init__(self, parent, -1, style=wx.NB_LEFT)

        self._services = remote.as_dict['services']
        self._pages = []

        for layout in self._services:
            service = getattr(remote, layout['name'])
            panel = ServicePanel(self, service, layout['methods'])

            self.InsertPage(0, panel, layout['name'])

        main_page = TVMainPage(self, remote)
        self.InsertPage(0, main_page, 'Main')


class GUI(wx.Frame):
    def __init__(self, config_path):
        wx.Frame.__init__(
            self,
            None,
            -1,
            size=(1400, 900),
            style=wx.DEFAULT_FRAME_STYLE
        )
        aui_manager = self.aui_manager = aui.AuiManager(
            self,
            (
                aui.AUI_MGR_ALLOW_FLOATING |
                aui.AUI_MGR_ALLOW_ACTIVE_PANE |
                aui.AUI_MGR_TRANSPARENT_DRAG |
                aui.AUI_MGR_TRANSPARENT_HINT |
                aui.AUI_MGR_HINT_FADE |
                aui.AUI_MGR_NO_VENETIAN_BLINDS_FADE |
                aui.AUI_MGR_WHIDBEY_DOCKING_GUIDES |
                aui.AUI_MGR_SMOOTH_DOCKING |
                aui.AUI_MGR_PREVIEW_MINIMIZED_PANES
            )
        )

        self._config_path = config_path
        self._loaded_configs = []
        self._ignore_configs = []
        log = self.log = LogPane(self)

        import samsungctl
        from samsungctl.upnp.discover import auto_discover

        # import logging

        # upnp_logger = logging.getLogger('UPNP_Device')
        # sam_logger = logging.getLogger('samsungctl')
        # upnp_logger.setLevel(logging.DEBUG)
        # sam_logger.setLevel(logging.DEBUG)

        pane_info = aui.AuiPaneInfo()

        pane_info.Caption("Log")
        pane_info.CaptionVisible(True)
        pane_info.Floatable(True)
        pane_info.Gripper(True)
        pane_info.Dockable(True)
        pane_info.CloseButton(False)
        pane_info.BestSize((1200, 300))
        pane_info.Bottom()

        aui_manager.AddPane1(log, pane_info)

        aui_manager.Update()
        self.Refresh()
        self.Update()
        pane_info.Show()

        self.count = 0

        for f in os.listdir(config_path):
            if not f.endswith('config'):
                continue

            f = os.path.join(config_path, f)
            config = samsungctl.Config.load(f)
            self._loaded_configs += [config]

            remote = samsungctl.Remote(config)
            remote.open()
            config.save()

            pane = TVPane(self, remote)
            pane_info = aui.AuiPaneInfo()

            pane_info.Caption(config.model)
            pane_info.CaptionVisible(True)
            pane_info.Floatable(True)
            pane_info.Gripper(True)
            pane_info.Dockable(True)
            pane_info.CloseButton(False)
            pane_info.BestSize((300, 500))
            pane_info.Center()

            aui_manager.AddPane1(pane, pane_info)

            aui_manager.Update()
            self.Refresh()
            self.Update()
            pane_info.Show()

        aui_manager.Update()
        # auto_discover.logging = True
        auto_discover.register_callback(self.discover_callback)
        auto_discover.start()
        remote_update.start()

    def discover_callback(self, config):

        for loaded_config in self._loaded_configs:
            if loaded_config == config:
                return

        for ignore_config in self._ignore_configs:
            if ignore_config == config:
                return

        event = threading.Event()

        def do():
            dialog = wx.MessageDialog(
                self,
                'Found TV {0},\nWould you like to add it?'.format(config.model),
                'Found TV',
                style=wx.ICON_QUESTION | wx.YES_NO | wx.NO_DEFAULT
            )

            answer = dialog.ShowModal()
            dialog.Destroy()

            if answer == wx.ID_YES:
                import samsungctl

                config.path = self._config_path
                remote = samsungctl.Remote(config)
                remote.open()
                config.save()

                pane = TVPane(self, remote)
                pane_info = aui.AuiPaneInfo()

                pane_info.Caption(config.model)
                pane_info.CaptionVisible(True)
                pane_info.Floatable(True)
                pane_info.Gripper(True)
                pane_info.Dockable(True)
                pane_info.CloseButton(False)
                pane_info.BestSize((300, 500))
                pane_info.Center()

                self.aui_manager.AddPane1(pane, pane_info)
                self.aui_manager.Update()
                pane.Show()
                self.Refresh()
                self.Update()
                pane_info.Show()
            else:
                self._ignore_configs += [config]

            event.set()

        wx.CallAfter(do)
        event.wait()


if __name__ == '__main__':
    frame = GUI(os.getcwd())
    frame.Show()

    app.MainLoop()




