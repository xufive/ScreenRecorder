# -*- coding:utf-8 -*-

import os, time
import optparse
import threading
import imageio
import queue
import numpy as np
from PIL import Image, ImageGrab
import win32gui, win32api, win32con
from pynput import keyboard, mouse

class PyTimer:
    """定时器类"""
    
    def __init__(self, func, *args, **kwargs):
        """构造函数"""
        
        self.func = func
        self.args = args
        self.kwargs = kwargs
        
        self.running = False
    
    def _run_func(self):
        """运行定时事件函数"""
        
        th = threading.Thread(target=self.func, args=self.args, kwargs=self.kwargs)
        th.setDaemon(True)
        th.start()
    
    def _start(self, interval, once):
        """启动定时器的线程函数"""
        
        if interval < 0.010:
            interval = 0.010
        
        if interval < 0.050:
            dt = interval/10
        else:
            dt = 0.005
        
        if once:
            deadline = time.time() + interval
            while time.time() < deadline:
                time.sleep(dt)
            
            # 定时时间到，调用定时事件函数
            self._run_func()
        else:
            self.running = True
            deadline = time.time() + interval
            while self.running:
                while time.time() < deadline:
                    time.sleep(dt)
                
                deadline += interval # 更新下一次定时时间
                if self.running: # 定时时间到，调用定时事件函数
                    self._run_func()
    
    def start(self, interval, once=False):
        """启动定时器
        
        interval    - 定时间隔，浮点型，以秒为单位，最高精度10毫秒
        once        - 是否仅启动一次，默认是连续的
        """
        
        th = threading.Thread(target=self._start, args=(interval, once))
        th.setDaemon(True)
        th.start()
    
    def stop(self):
        """停止定时器"""
        
        self.running = False

class ScreenRecorder:
    """屏幕记录器"""
    
    def __init__(self, out, fps=10, nfs=1000, loop=0):
        """构造函数"""
        
        self.format = ('.gif', '.mp4', '.avi', '.wmv')
        
        ext = os.path.splitext(out)[1].lower()
        if not ext in self.format:
            raise ValueError('不支持的文件格式：%s'%ext)
        
        self.out = out
        self.ext = ext
        self.fps = fps
        self.nfs = nfs
        self.loop = loop
        
        self.cw = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
        self.ch = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
        self.set_box((0, 0, self.cw, self.ch))
        
        self.ctr_is_pressed = False
        self.hidding = False
        self.recording = False
        self.pos_click = (0,0)
        self.q = None
        
        self.hwnd = self._find_self()
        self.info = None
        self.help()
        self.status()
    
    def _find_self(self):
        """找到当前Python解释器的窗口句柄"""
        
        return win32gui.GetForegroundWindow() # 获取最前窗口句柄
    
    def set_box(self, box):
        """设置记录区域"""
        
        x0, y0, x1, y1 = box
        dx, dy = (x1-x0)%16, (y1-y0)%16
        dx0, dx1 = dx//2, dx-dx//2
        dy0, dy1 = dy//2, dy-dy//2
        
        self.box = (x0+dx0, y0+dy0, x1-dx1, y1-dy1)
    
    def help(self):
        """热键提示"""
        
        print('---------------------------------------------')
        print('Ctr + 回车键：隐藏/显示窗口')
        print('Ctr + 鼠标左键或右键拖拽：设置记录区域')
        print('Ctr + PageUp/PageDown：更改记录格式')
        print('Ctr + Up/Down：调整帧率')
        print('Ctr + 空格键：开始/停止记录')
        print('Esc：退出')
        print()
    
    def status(self):
        """当前状态"""
        
        if self.info:
            print('\r%s'%(' '*len(self.info.encode('gbk')),), end='', flush=True)
        
        recording_text = '正在记录' if self.recording else '准备就绪'
        if self.ext == 'gif':
            loop_str = '循环%d次'%self.loop if self.loop > 0 else '循环'
        else:
            loop_str = '不循环'
        
        self.info = '\r输出文件：%s | 帧率：%d | 区域：%s'%(self.out, self.fps, str(self.box))
        print(self.info, end='', flush=True)
    
    def start(self):
        """开始记录"""
        
        self.q = queue.Queue(100)
        self.timer = PyTimer(self.capture)
        self.timer.start(1/self.fps)
        
        th = threading.Thread(target=self.produce)
        th.setDaemon(True)
        th.start()
    
    def stop(self):
        """停止记录"""
        
        self.timer.stop()
    
    def capture(self):
        """截屏"""
        
        if not self.q.full():
            im = ImageGrab.grab(self.box)
            self.q.put(im)
    
    def produce(self):
        """生成动画或视频文件"""
        
        if self.ext == '.gif':
            writer = imageio.get_writer(self.out, fps=self.fps, loop=self.loop)
        else:
            writer = imageio.get_writer(self.out, fps=self.fps)
        
        n = 0
        while self.recording and n < self.nfs:
            if self.q.empty():
                time.sleep(0.01)
            else:
                im = np.array(self.q.get())
                writer.append_data(im)
                n += 1
        
        writer.close()
    
    def on_press(self, key):
        """键按下"""
        
        if key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
            self.ctr_is_pressed = True
    
    def on_release(self, key):
        """键释放"""
        
        if key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
            self.ctr_is_pressed = False
        elif key == keyboard.Key.space and self.ctr_is_pressed:
            if self.recording: # 停止记录
                self.stop()
                self.recording = False
                if self.hidding:
                    win32gui.ShowWindow(self.hwnd, win32con.SW_SHOW) # 显示窗口
                    self.hidding = False
            else: # 开始记录
                self.start()
                self.recording = True
                if not self.hidding:
                    win32gui.ShowWindow(self.hwnd, win32con.SW_HIDE) # 隐藏窗口
                    self.hidding = True
        elif key == keyboard.Key.enter and self.ctr_is_pressed:
            if self.hidding: # 显示窗口
                win32gui.ShowWindow(self.hwnd, win32con.SW_SHOW) # 显示窗口
                self.hidding = False
                self.status()
            else: # 隐藏窗口
                win32gui.ShowWindow(self.hwnd, win32con.SW_HIDE) # 隐藏窗口
                self.hidding = True
        elif (key == keyboard.Key.page_down or key == keyboard.Key.page_up) and self.ctr_is_pressed:
            i = self.format.index(self.ext)
            if key == keyboard.Key.page_down:
                self.ext = self.format[(i+1)%len(self.format)]
            else:
                self.ext = self.format[(i-1)%len(self.format)]
            
            folder = os.path.split(self.out)[0]
            dt_str = time.strftime('%Y%m%d%H%M%S')
            self.out = os.path.join(folder, '%s%s'%(dt_str, self.ext))
            self.status()
        elif key == keyboard.Key.left and self.ctr_is_pressed:
            if self.fps > 1:
                self.fps -= 1
                self.status()
        elif key == keyboard.Key.right and self.ctr_is_pressed:
            if self.fps < 40:
                self.fps += 1
                self.status()
        elif key == keyboard.Key.esc:
            print('\n程序已结束')
            return False
    
    def on_click(self, x, y, button, pressed):
        """鼠标按键"""
        
        if (button == mouse.Button.left or button == mouse.Button.right) and self.ctr_is_pressed:
            if pressed:
                self.pos_click = (x, y)
            elif self.pos_click != (x, y):
                x0, y0 = self.pos_click
                self.set_box((min(x0,x), min(y0,y), max(x0,x), max(y0,y)))
                self.status()

def parse_args():
    """获取参数"""

    parser = optparse.OptionParser()
    
    parser.add_option('-o', '--out', action='store', type='string', dest='out', default='', help='输出文件名')
    parser.add_option('-f', '--fps', action='store', type='int', dest='fps', default='10', help='帧率')
    parser.add_option('-n', '--nfs', action='store', type='int', dest='nfs', default='1000', help='最大帧数')
    parser.add_option('-l', '--loop', action='store', type='int', dest='loop', default=0, help='循环')
    
    return parser.parse_args()

if __name__ == '__main__':

    options, args = parse_args()
    
    if options.out:
        out = options.out
        folder = os.path.split(out)[0]
        if folder and not os.path.isdir(folder):
            raise ValueError('路径不存在：%s'%folder)
    else:
        dt_str = time.strftime('%Y%m%d%H%M%S')
        out = os.path.join(os.getcwd(), '%s.mp4'%(dt_str,))
    
    sr = ScreenRecorder(out, fps=options.fps, nfs=options.nfs, loop=options.loop)
    
    monitor_m = mouse.Listener(on_click=sr.on_click)
    monitor_m.start()
    
    monitor_k = keyboard.Listener(on_press=sr.on_press, on_release=sr.on_release)
    monitor_k.start()
    monitor_k.join()



