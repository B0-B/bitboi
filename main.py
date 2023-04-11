# bitboi v6.1 software © 2023
# Source Code Licensed under MIT.
# Copyright © 2023 github.com/B0-B

# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the “Software”), to deal in the
# Software without restriction, including without limitation the rights to use, copy,
# modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the
# following conditions:
# 
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

# modules are all built-in
# ssd1306 can be installed via thonny, or downloaded here:
# https://github.com/stlehmann/micropython-ssd1306/blob/master/ssd1306.py
#import socket
import gc
import network
import socket
import _thread
from utime import sleep
from machine import Pin, I2C
from ssd1306 import SSD1306_I2C
from math import sqrt, log
from framebuf import FrameBuffer, MONO_HLSB
import urequests as requests
import json


################## parameters #################
# =============================================
# Do not change these parameters, otherwise
# this could short the display!
WIDTH = 128
HEIGHT = 64
scl_pin = 19
sda_pin = 18
vcc_pin = 20
gnd_pin = 21
# =============================================

# market 
INTERVAL = 60               # interval unit in minutes (e.g. a day = 1440 minutes)
EPOCH = 128					# a value for each pixel - number of values seperated by interval (too large values can overload memory)
TREND_INTERVALS = 12        # how many intervals for trend window
REFERENCE = 'USD'			# reference currency
UPDATE =  30                # OHLC request delay in seconds
SYNC = 12					# syncing period in hours
krakenReference = {			# reference symbols for kraken api
    'bitcoin': 'XBT',
    'ethereum': 'ETH',
    'ethereum-pow': 'ETHW',
    'filecoin': 'FIL',
    'monero': 'XMR'
}
DISPLAY_MODES = [
    'chart',
    'indicate'
    
]
################################################

# -- emulate necessary pins for display --
# emulate VCC on pin 20
VCC = Pin(vcc_pin, Pin.OUT)
VCC.value(1)

# emulate GND on pin 21
GND = Pin(gnd_pin, Pin.OUT)
GND.value(0)

# init global wifi object
wifi = network.WLAN(network.STA_IF)


# -- bootsel module --
def bootsel_is_pressed ():
    
    '''
    Returns boolean corresponding to bootsel high/low state.
    '''
    
    return not read_bootsel()

@micropython.asm_thumb
def read_bootsel():
    
    '''
    Pragmatic assembly implementation which reads the bootsel state.
    Credit to github@pdg137
    https://github.com/micropython/micropython/issues/6852#issuecomment-1350081346
    '''
    
    # disable interrupts
    cpsid(0x0)    
    # set r2 = addr of GPIO_QSI_SS registers, at 0x40018000
    # GPIO_QSPI_SS_CTRL is at +0x0c
    # GPIO_QSPI_SS_STATUS is at +0x08
    # is there no easier way to load a 32-bit value?
    mov(r2, 0x40)
    lsl(r2, r2, 8)
    mov(r1, 0x01)
    orr(r2, r1)
    lsl(r2, r2, 8)
    mov(r1, 0x80)
    orr(r2, r1)
    lsl(r2, r2, 8)    
    # set bit 13 (OEOVER[1]) to disable output
    mov(r1, 1)
    lsl(r1, r1, 13)
    str(r1, [r2, 0x0c])   
    # delay about 3us
    # seems to work on the Pico - tune for your system
    mov(r0, 0x16)
    label(DELAY)
    sub(r0, 1)
    bpl(DELAY)    
    # check GPIO_QSPI_SS_STATUS bit 17 - input value
    ldr(r0, [r2, 0x08])
    lsr(r0, r0, 17)
    mov(r1, 1)
    and_(r0, r1)    
    # clear bit 13 to re-enable, or it crashes
    mov(r1, 0)
    str(r1, [r2, 0x0c])   
    # re-enable interrupts
    cpsie(0x0)


# -- load I2C connection --
i2c = I2C(1, scl=Pin(scl_pin), sda=Pin(sda_pin), freq=200000)
oled = SSD1306_I2C(WIDTH, HEIGHT, i2c)

def buttonIsPressed ():
    
    return bootsel_is_pressed()

def connectToWifi ():
    
    '''
    Will connect to the first possible profile (with SSID and WPA2) in wifi.json.
    Profiles at the top are tried first (1st prio). Will jump into a loop until a connection is est.
    If the data in wifi.json is still stock, a setup is displayed.
    '''
    
    # try to load wifi.json
    try:
        with open('wifi.json') as f:
            JSON = json.load(f)
    except:
        printDisplay('could not load wifi.json file ...', clean=True)
        raise FileNotFoundError('wifi.json')
    
    # extract profile names
    profileNames = list(JSON.keys())
    
    # check if at least a profile was provided
    if len(profileNames) == 0:
        printDisplay('no wifi profiles provided in wifi.json', clean=True)
    
    # check if a profile was configured at all
    if len(profileNames) == 2 and JSON[profileNames[0]]['wpa2'] == 'twerky1' and JSON[profileNames[1]]['wpa2'] == 'twerky2':
        printDisplay('Hi, there!', clean=True)
        sleep(3)
        printDisplay('I am bitboi, a tiny crypto ticker.', clean=True)
        sleep(4)
        printDisplay('To set me up, follow these steps:', clean=True)
        sleep(4)
        # display the setup steps in a loop
        steps = [
            '1. Connect me to your computer and download thonny from thonny.org',
            '2. In thonny select "MicroPython (Rasperry Pi Pico)" in the lower right corner.',
            '3. Open wifi.json in the directory on the left in thonny.',
            '4. Add wifi profiles with your SSID and WPA2 password',
            '5. Save the file, and plug me to any USB or power bank',
            "6. Let's have some fun!",
            "If you press the button once you can cycle through all symbols.",
            "Double click and keep pressed cycles back."
        ]
        while True:
            for step in steps:
                printDisplay(step, clean=True)
                sleep(5)
        exit()
    
    # iterate through profiles, starting from top until a connection succeeds
    connected = False
    while not connected:
    
        for name, cred in JSON.items():
            
            try:
                
                printDisplay(f'Connect to {name} ...', clean=True)
                sleep(1)
                
                # initiliaze wifi adapter
                #wifi = network.WLAN(network.STA_IF)
                wifi.active(True)
                
                # disable powersave mode to make the wifi more responsive
                wifi.config(pm = 0xa11140)
                
                # try to connect
                wifi.connect(cred['ssid'], cred['wpa2'])
                
                # exit
                connected = True
                printDisplay(f'Connected WiFi:', clean=True)
                printDisplay(name, startLine=1, clean=False)
                
                sleep(2)
                break
            
            except:
                
                printDisplay(f'{name} failed.', clean=True)
                sleep(2)


# -- I2C methods --
def showLogo (time=2):
    
    '''
    Displays logo for a specific amount of time.
    '''
    
    logoData = bytearray(b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x07\x80\x00\x00\x00\x00\x00\x00\x3c\x00\x00\x00\x00\x00\x00\x00\x07\x80\x00\x00\x00\x00\x00\x00\x3c\x00\x00\x00\x00\x00\x00\x00\x07\x80\x00\x00\x00\x00\x00\x00\x3c\x00\x00\x00\x00\x00\x00\x00\x07\x80\x00\x00\x00\x00\x00\x00\x3c\x00\x00\x00\x00\x00\x00\x00\x07\x80\x00\x00\x00\x00\x00\x00\x3c\x00\x00\x00\x00\x00\x00\x00\x07\x80\x00\x00\x00\x00\x00\x00\x3c\x00\x00\x00\x00\x00\x00\x00\x07\x80\x00\x00\x00\x00\x00\x00\x3c\x00\x00\x00\x00\x00\x00\x00\x07\x80\x00\x00\x00\x00\x00\x00\x3c\x00\x00\x00\x00\x00\x00\x00\x07\xff\xff\x80\xe1\xff\xff\xfc\x3f\xff\xfc\x00\xff\xff\x81\xe0\x07\xff\xff\xc0\xe1\xff\xff\xfc\x3f\xff\xff\x03\xff\xff\xc1\xe0\x07\xff\xff\xe0\xe1\xff\xff\xfc\x3f\xff\xff\x03\xff\xff\xe1\xe0\x07\xff\xff\xf0\xe1\xff\xff\xfc\x3f\xff\xff\x87\xff\xff\xe1\xe0\x07\x80\x01\xf0\xe1\xe0\x00\x00\x3c\x00\x07\x87\x80\x01\xe1\xe0\x07\x80\x00\xf0\xe1\xe0\x00\x00\x3c\x00\x07\x87\x80\x00\xf1\xe0\x07\x80\x00\xf0\xe1\xe0\x00\x00\x3c\x00\x07\x87\x80\x00\xf1\xe0\x07\x80\x00\xf0\xe1\xe0\x00\x00\x3c\x00\x07\x87\x80\x00\xf1\xe0\x07\x80\x00\xf0\xe1\xe0\x00\x00\x3c\x00\x07\x87\x80\x00\xf1\xe0\x07\x80\x00\xf0\xe1\xe0\x00\x00\x3c\x00\x07\x87\x80\x00\xf1\xe0\x07\x80\x00\xf0\xe1\xe0\x00\x00\x3c\x00\x07\x87\x80\x00\xf1\xe0\x07\x80\x00\xf0\xe1\xe0\x00\x00\x3c\x00\x07\x87\x80\x00\xf1\xe0\x07\x80\x00\xf0\xe1\xe0\x00\x00\x3c\x00\x07\x87\x80\x00\xf1\xe0\x07\x80\x00\xf0\xe1\xe0\x00\x00\x3c\x00\x07\x87\x80\x01\xe1\xe0\x07\xc0\x01\xf0\xe0\xf0\x00\x00\x3e\x00\x0f\x87\x80\x01\xe1\xe0\x03\xff\xff\xe0\xe0\xff\xe0\x00\x1f\xff\xff\x07\xff\xff\xe1\xe0\x03\xff\xff\xe0\xe0\xff\xe0\x00\x1f\xff\xff\x03\xff\xff\xc1\xe0\x01\xff\xff\xc0\xe0\x7f\xe0\x00\x0f\xff\xfe\x01\xff\xff\x81\xe0\x00\x7f\xff\x00\xe0\x1f\xc0\x00\x03\xff\xf8\x00\x7f\xff\x00\xe0\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00')
    fb = FrameBuffer(logoData, WIDTH, HEIGHT, MONO_HLSB)
    oled.fill(0)
    oled.blit(fb, 0, 0)
    oled.show()
    sleep(time)
    oled.fill(0)

def text (output, lineHeight=10, lineLength=15, startLine=0):

    '''
    displays text on oled display
    '''
    
    line = startLine
    current_line = ''
    
    for i in range(len(output)):
        current_line += output[i]
        if (i % lineLength == 0 and i > 0) or i == len(output)-1:
            oled.text(current_line, 0, int(line*lineHeight))
            line += 1
            current_line = ''
        
    oled.show()

def printDisplay (output, clean=True, startLine=0):
    
    '''
    Prints in terminal and OLED display.
    '''
    
    if clean:
        oled.fill(0)
    text(output, startLine=startLine)
    print(output)
    
def plotChart (oled, data, height=30, y=0):
    
    '''
    plots the data to chart.
    Origin is at the lower left corner.
    '''
    
    if len(data) > 128:    
        ValueError('data array too large for plotting, must have <=128 values.')
        
    # invert y coord
    y = 64 - y
    
    plotData = [None for i in range(128-len(data))]
            
    
    # scale timeseries to display pixel size
    bounds = [min(data), max(data)]
    _range = bounds[1] - bounds[0]
    for i in range(len(data)):
        normalized = (data[i]-bounds[0]) / _range
        plotData.append(int(normalized*height))
    
    for i in range(1,len(plotData)):
        if plotData[i]:
            oled.pixel(i, y-plotData[i], 1)
            dy = plotData[i]-plotData[i-1]
            if dy != 0:
                s = int(dy / abs(dy))
            for j in range(1,abs(dy)):
                oled.pixel(i, y-plotData[i]+s*j, 1)


# -- trading API and stats --    
class krakenApi:

    '''
    Loads crypto price data from kraken rest API.
    Returns list of candle lists (time,o,h,l,c,avg,volume).
    '''

    krakenUrl = 'https://futures.kraken.com'
    
    def getSymbols (ref='USD', startedList={}):
        
        while True:
            try:
                pkg = requests.get('https://api.kraken.com/0/public/AssetPairs?info=margin').json()['result']
                symbolList = list(pkg.keys())
                break
            except:
                print('Failed to fetch asset pairs try again')
                sleep(1)

        for symbol in symbolList:
            if ref in str(symbol):
                name = symbol.upper().split(ref)[0]
                if len(name) > 0 and name not in startedList.values():
                    startedList[name] = name
        
        return startedList
    
    def history (symbol, interval, epoch=30, ref='USD'):

        '''
        Requests OHLC timeseries data 720 points of chosen time intervals in minutes.
        '''
        
        # get corresponding server time and compute since
        pkg = requests.get("https://api.kraken.com/0/public/Time").json()
        if len(pkg['error']) > 0:
            raise ValueError(pkg['error'][0])
        serverTime = pkg['result']['unixtime'] 
        sleep(1)
        since = serverTime - epoch * INTERVAL * 60
        
        # make history request
        pkg = requests.get(f'https://api.kraken.com/0/public/OHLC?pair={krakenReference[symbol]}{ref}&interval={interval}&since={since}').json()
        if len(pkg['error']) > 0:
            raise ValueError(pkg['error'][0])
        
        
        # unpack
        closed = []
        for name in pkg['result'].keys():
            if krakenReference[symbol] in name.upper():
                ohlcData = pkg['result'][name]
                break
        for i in range(len(ohlcData)):
            closed.append(float(ohlcData[i][4]))
        
        return closed
    
def updateSymbolReference ():
    
    '''
    Updates the krakenReference with all other symbols found on kraken.
    '''
    
    while True:
        try:
            krakenReference = krakenApi.getSymbols(REFERENCE, krakenReference)
            break
        except Exception as e:
            print(e)
            sleep(.5)
            

def drift (history, window):
    
    '''
    Returns the geometric brownian motion drift meaned oved the recent window interval.
    The unit is given as relative price change in [%/interval]
    '''
    
    d = 0
    snippet = history[-window:]
    for i in range(len(snippet)-1):
        d += log(snippet[i+1]/snippet[i])
    return d/(window-1)

def volatility (history, drift, window):
    
    '''
    Returns the volatility meaned accross a requested window.
    Estimated from the standard deviation of logarithmic returns and using
    the drift as expectation. The drift needs to be pre-computed.
    '''
    
    var = 0
    snippet = history[-window:]
    for i in range(len(snippet)-1):
        var += (log(snippet[i+1]/snippet[i]) - drift) ** 2
    var /= window - 1 # sample variance correction
    vol = sqrt(var) # std deviation from var
    
    return vol

def digits (number, n):
    
    '''
    Rounds number to significant digits.
    Starts counting from the first non-zero digit.
    '''
    
    stringed = str(number)
    new = ''
    count = 0
    for sym in stringed:
        if not (count == 0 and sym == '0') and sym != '.':
            count += 1
        new += sym
        if count == n:
            break
    return float(new)


# -- ticker main loop --   
def multiTicker (startSymbols, update=30):
    
    '''
    Live crypto ticker implementation with symbol switching button.
    '''
    
    updateCount = 0
    printDisplay('sync tradable symbols ...')
    
    # update krakenReference
    krakenReference = krakenApi.getSymbols('USD', startSymbols)
    
    # extract the symbols for reference
    symbols = list(krakenReference.keys())
    sym_ind = symbols.index('bitcoin')
    symbol = symbols[sym_ind]
    
    # alter display mode at every cycle
    alter = 0
    
    leftPadding = 5
    intervals_per_day = int(1440/INTERVAL)
    intervals_per_hour = int(60/INTERVAL)
    
    printDisplay('start ticker ...')
    
    
    # Every while loop cycle is a tick
    while True:
        
        try:
            
            # request most recent price history 
            history = krakenApi.history(symbol, INTERVAL, EPOCH, ref=REFERENCE)
            
            
            # check if the symbol has a significant history first
            if len(history) < TREND_INTERVALS + 1:
                
                printDisplay(f'not enough data for {symbol} yet.')
            
            else:
                
                # build title line
                oled.fill(0) # clean old state
                # draw symbol background
                oled.fill_rect(0, 0, 127, 10, 1)  
                center_padding_length = int((16-len(symbol))/2)
                center_padding = ''.join([' ' for i in range(center_padding_length)])
                oled.text(center_padding + symbol.upper(), 0, 2, 0)
                
                # extract price
                price = digits(history[-1], 5)
                
                # show chart
                if DISPLAY_MODES[alter] == 'indicate':
                    
                    # compute statistics
                    d = drift(history, TREND_INTERVALS)
                    d_h = round(100 * d / intervals_per_hour, 2)
                    v = volatility(history, d, TREND_INTERVALS)
                    v_h = round(100*v/sqrt(intervals_per_hour),2) # see https://en.wikipedia.org/wiki/Volatility_(finance)#Mathematical_definition
                    change_24h = round(100 * (history[-1] / history[-intervals_per_day] - 1), 1)
                    sign = ['+', ''][change_24h < 0]
                    
                    # build price line with 24h return 
                    priceLine = f'${price} {sign}{change_24h}%'
                    
                    # build ROI line from 1h drift
                    roiLine = f'ROI: {['+', ''][d < 0]}{d_h} %/h'
                    
                    # build volatility line
                    volLine = f'VOL: {v_h} %/h'
                    
                    # add assembled lines
                    oled.text(priceLine, leftPadding , 15)
                    oled.text(roiLine, leftPadding , 30)
                    oled.text(volLine, leftPadding , 45)
                
                # show chart
                elif DISPLAY_MODES[alter] == 'chart':
                    
                    # compute change for price line only
                    change_24h = round(100 * (history[-1] / history[-intervals_per_day] - 1), 1)
                    sign = ['+', ''][change_24h < 0]
                    
                    # build price line with 24h return 
                    priceLine = f'${price} {sign}{change_24h}%'
                    
                    # add price line
                    oled.text(priceLine, leftPadding, 15)
                    
                    # plot chart below
                    plotChart (oled, history, height=32, y=3)
                
                # iterate
                alter = (alter + 1) % len(DISPLAY_MODES)
                    
                    
                
                # send to display
                oled.show()
            
            # simulate listener for button
            continuousDelayTime = 300 # in ms
            doubleClickHookTime = 200 # in ms
            doubleClickResponseTime = 1000 # in ms
            dt = 0.005
            for i in range(int(update/dt)):
                
                # check if button is pressed in this loop
                entered_loop = False
                clickPattern = '' # init click pattern for this tick cylce
                while buttonIsPressed():
                    
                    # check for double clicks first
                    # wait for double click
                    for i in range(doubleClickHookTime):
                        sleep(0.001)
                        if not buttonIsPressed():
                            clickPattern += '0'
                            break
                    if clickPattern == '0':
                        for i in range(doubleClickResponseTime):
                            sleep(0.001)
                            if buttonIsPressed():
                                clickPattern += '1'
                                break
                    prop = 'to'
                    if clickPattern == '01':
                        prop = 'back'
                        if sym_ind == 0:
                            sym_ind = len(symbols)-1
                        else:
                            sym_ind -= 1
                    
                    # otherwise if no double click was detected,
                    # raise the symbol index in cyclic fashion
                    else:
                        sym_ind = (sym_ind+1)%len(symbols)
                    
                    try:
                        symbol = symbols[sym_ind]
                        oled.fill(0)
                        text(f'switch {prop}')
                        text(symbol, startLine=2)
                        sleep(continuousDelayTime*.001)
                        entered_loop = True
                    except Exception as e:
                        print('button error:', e)
                                                                                                                                      
                # kill the for loop right away if a selection was made
                if entered_loop:
                    break
                
                sleep(dt)
            
            # clean up after each tick
            gc.collect()
                
        except Exception as e:
            
            print('***ERROR***:', str(e))
            
            errorString = str(e).lower()
            
            if ('conn' in errorString or 'http' in errorString or 'timeout' in errorString):
                printDisplay('lost connection, reconnect ...')
            else:
                printDisplay('Some anomalies ...')
            
        finally:
            
            # increment the update count for symbols
            updateCount += update
            
            # if threshold of e.g. a day is reached update
            if updateCount - SYNC*3600 > 0:
                
                # update symbols
                try:
                    printDisplay('update symbols ...')
                    krakenReference = krakenApi.getSymbols('USD', startSymbols)
                    symbols = list(krakenReference.keys())
                    updateCount = 0
                except Exception as e:
                    print('Symbol update error:',e)
                
                # clean up
                
                    
            sleep(1)
        

# -- version updater --
# updates will be queried from github pages ()
# the mini CICD pipeline will be triggered once every sync period
# or at start to query the current version on main branch

__version__ = 'v6.1'
github_pages_target = 'https://raw.githubusercontent.com/B0-B/bitboi/main/main.py'
def CICD ():

    '''
    Tiny CICD pipeline implementation
    '''

    printDisplay('Found new version, do you want to install it? (yes)')
    printDisplay('Updating ...')

    code = requests.get()



# -- webserver --
# for future development


def main ():

    '''
    Main orchestration.
    '''
    
    showLogo(3)
    connectToWifi()
    multiTicker(krakenReference, UPDATE)


if __name__ == '__main__':
    main()
