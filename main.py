#####################################################################################
#####################################################################################
# Main Code © 2024
# Copyright © 2024 github.com/B0-B

# This program allows to orchestrate all needed modules:
# - main program
# - captive portal
#####################################################################################
#####################################################################################

__version__ = 'v7.0'
github_pages_target = 'https://raw.githubusercontent.com/B0-B/bitboi/main/main.py'
github_feed_target = 'https://raw.githubusercontent.com/B0-B/bitboi/main/news'

#####################################################################################

import gc, json, sys, _thread
import urequests as requests
from math import sqrt, log
from portal import spawn
from utime import sleep
from network import WLAN, STA_IF
from machine import Pin, I2C, reset
from ssd1306 import SSD1306_I2C
from framebuf import FrameBuffer, MONO_HLSB

# ============= Parameters ==============
# Pages which alternate on display
PAGE = 0
DISPLAY_PAGES = ['chart', 'statistics']

# ---- I2C pin-out ----
# Do not change these parameters, otherwise
# this could short the display!
WIDTH = 128
HEIGHT = 64
scl_pin = 19
sda_pin = 18
vcc_pin = 20
gnd_pin = 21
# display geometry (this can be changed)
leftPadding = 5

# ---- kraken API ----
krakenReference = {			
    'bitcoin': 'XBT',
    'ethereum': 'ETH'
}

class news:
    feed = ''

# ---- load config ----
with open('config.json') as f:
    _config = json.load(f)
# convert to variables
EPOCH = 128					                    # a value for each pixel - number of values seperated by interval (too large values can overload memory)
INTERVAL = _config['interval']                  # interval unit in minutes (e.g. a day = 1440 minutes)
TREND_INTERVALS = _config['trend_intervals']    # how many intervals for trend window
REFERENCE = _config['reference']			    # reference currency
COIN = _config['coin']                      	# selected kraken ticker symbol
UPDATE =  15                                    # OHLC request delay in seconds

# ============= Load Modules ==============
# ---- load I²C connection ----
# emulate necessary pins for display
# emulate VCC on pin 20
VCC = Pin(vcc_pin, Pin.OUT)
VCC.value(1)
# emulate GND on pin 21
GND = Pin(gnd_pin, Pin.OUT)
GND.value(0)
# init I²C
i2c = I2C(1, scl=Pin(scl_pin), sda=Pin(sda_pin), freq=200000)
oled = SSD1306_I2C(WIDTH, HEIGHT, i2c)
# ---- init wifi ----
wifi = WLAN(STA_IF)
wifi_connected = False

# ============= Methods ==============
# ---- bootsel button exploit ----
def bootsel_is_pressed ():
    
    '''
    Inverse alias of read_bootsel().
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


# ---- I²C methods ----
def clear ():
    
    '''
    Clears display.
    '''
    
    oled.fill(0)
    
def trademark (time=2):
    
    '''
    Displays trademark logo for a provided amount of time.
    '''
    
    logoData = bytearray(b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x07\x80\x00\x00\x00\x00\x00\x00\x3c\x00\x00\x00\x00\x00\x00\x00\x07\x80\x00\x00\x00\x00\x00\x00\x3c\x00\x00\x00\x00\x00\x00\x00\x07\x80\x00\x00\x00\x00\x00\x00\x3c\x00\x00\x00\x00\x00\x00\x00\x07\x80\x00\x00\x00\x00\x00\x00\x3c\x00\x00\x00\x00\x00\x00\x00\x07\x80\x00\x00\x00\x00\x00\x00\x3c\x00\x00\x00\x00\x00\x00\x00\x07\x80\x00\x00\x00\x00\x00\x00\x3c\x00\x00\x00\x00\x00\x00\x00\x07\x80\x00\x00\x00\x00\x00\x00\x3c\x00\x00\x00\x00\x00\x00\x00\x07\x80\x00\x00\x00\x00\x00\x00\x3c\x00\x00\x00\x00\x00\x00\x00\x07\xff\xff\x80\xe1\xff\xff\xfc\x3f\xff\xfc\x00\xff\xff\x81\xe0\x07\xff\xff\xc0\xe1\xff\xff\xfc\x3f\xff\xff\x03\xff\xff\xc1\xe0\x07\xff\xff\xe0\xe1\xff\xff\xfc\x3f\xff\xff\x03\xff\xff\xe1\xe0\x07\xff\xff\xf0\xe1\xff\xff\xfc\x3f\xff\xff\x87\xff\xff\xe1\xe0\x07\x80\x01\xf0\xe1\xe0\x00\x00\x3c\x00\x07\x87\x80\x01\xe1\xe0\x07\x80\x00\xf0\xe1\xe0\x00\x00\x3c\x00\x07\x87\x80\x00\xf1\xe0\x07\x80\x00\xf0\xe1\xe0\x00\x00\x3c\x00\x07\x87\x80\x00\xf1\xe0\x07\x80\x00\xf0\xe1\xe0\x00\x00\x3c\x00\x07\x87\x80\x00\xf1\xe0\x07\x80\x00\xf0\xe1\xe0\x00\x00\x3c\x00\x07\x87\x80\x00\xf1\xe0\x07\x80\x00\xf0\xe1\xe0\x00\x00\x3c\x00\x07\x87\x80\x00\xf1\xe0\x07\x80\x00\xf0\xe1\xe0\x00\x00\x3c\x00\x07\x87\x80\x00\xf1\xe0\x07\x80\x00\xf0\xe1\xe0\x00\x00\x3c\x00\x07\x87\x80\x00\xf1\xe0\x07\x80\x00\xf0\xe1\xe0\x00\x00\x3c\x00\x07\x87\x80\x00\xf1\xe0\x07\x80\x00\xf0\xe1\xe0\x00\x00\x3c\x00\x07\x87\x80\x01\xe1\xe0\x07\xc0\x01\xf0\xe0\xf0\x00\x00\x3e\x00\x0f\x87\x80\x01\xe1\xe0\x03\xff\xff\xe0\xe0\xff\xe0\x00\x1f\xff\xff\x07\xff\xff\xe1\xe0\x03\xff\xff\xe0\xe0\xff\xe0\x00\x1f\xff\xff\x03\xff\xff\xc1\xe0\x01\xff\xff\xc0\xe0\x7f\xe0\x00\x0f\xff\xfe\x01\xff\xff\x81\xe0\x00\x7f\xff\x00\xe0\x1f\xc0\x00\x03\xff\xf8\x00\x7f\xff\x00\xe0\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00')
    fb = FrameBuffer(logoData, WIDTH, HEIGHT, MONO_HLSB)
    clear()
    oled.blit(fb, 0, 0)
    oled.show()
    sleep(time)
    clear()

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

def print_display (output, clean=True, startLine=0):
    
    '''
    Prints in terminal and OLED display.
    '''
    
    if clean:
        clear()
    text(output, startLine=startLine)
    print(output)
    
def plot_chart (oled, data, height=30, y=0):
    
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

def center (output, lineHeight=10, pad_x=0, pad_y=0, delay=.2):
    current_line = ''
    line = 0
    for i in range(len(output)):
        current_line += output[i]
        if (i % 15 == 0 and i > 0) or (delay==0 and i == len(output)-1):
            oled.text(current_line, pad_x, int(line*lineHeight) + pad_y)
            line += 1
            current_line = ''
        if delay > 0:
            clear()
            oled.text(current_line, pad_x, int(line*lineHeight) + pad_y)
            oled.show()
        sleep(delay)
    oled.show()
    
# ---- trading API and stats ----    
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
        pkg = requests.get(f'https://api.kraken.com/0/public/OHLC?pair={symbol}{ref}&interval={interval}&since={since}', timeout=10).json()
        if len(pkg['error']) > 0:
            raise ValueError(pkg['error'][0])
        
        
        # unpack
        closed = []
        for name in pkg['result'].keys():
            if symbol.upper() in name.upper():
                ohlcData = pkg['result'][name]
                break
        for i in range(len(ohlcData)):
            closed.append(float(ohlcData[i][4]))
        
        return closed
            
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

# ---- sequences ----
# CICD pipeline
def auto_update ():

    '''
    Tiny CICD pipeline.
    Checks queried content from github pages
    and updates the code if newer version was found.
    '''

    # request latest code
    code = None
    for i in range(5):
        try:
            response = requests.get(github_pages_target)
            code = str(response.text)
            break
        except Exception as e:
            print('failed to request latest version, try again ...')
            sleep(.2)
    if not code:
        return
    
    # parse out version
    lines = code.split('\r\n')
    newVersion = ''
    for line in lines:
        if '__version__' in line:
            latest = line.split(' ')[-1].replace("'","")
            if __version__ == latest:
                # do nothing if versions don't differ
                return
            newVersion = latest
            break
    
    # seconds counter for confirmation
    count = 5
    updateConfirmed = False
    for s in range(count):
        print_display(f'Should I update to new version {newVersion}? Press button for "yes" ({count-s}s)')
        # wait for 1 second and listen for input
        for i in range(1000):            
            if bootsel_is_pressed():
                updateConfirmed = True
                break
            sleep(.001)
    
    # confirmed
    if updateConfirmed:
        print_display(f'Updating to version {newVersion} ...')
        sleep(1)
        with open('./main.py', 'w+') as file:
            file.write(code)
        print_display(f'Thanks for updating me! :)')
        sleep(3)
        reset()

def welcome ():
    
    '''
    Little welcome sequence.
    '''
    
    delay = 3
    typeDelay = 0.1
    center('HELLO :)', 10, 40, 24, typeDelay)
    sleep(delay)
    center("I am bitboi", 10, 20, 24, typeDelay)
    sleep(delay)
    center("a crypto ticker", 10, 0, 24, typeDelay)
    sleep(delay)
    center("Wi-Fi: bitboi", 10, 10, 24, typeDelay)
    sleep(delay)

def load_news_feed ():
    
    # draw current news document from github pages
    data = requests.get(github_feed_target).text
    received_feed = str(data).replace('\n', ' ') + ' '

    # override global feed if payload differs
    return received_feed
     
def show_news_feed_window (feed_pointer, news_window):
    
    '''
    Displays current windown of news feed string, based on pointer.
    '''

    window = ''
    for inc in range(news_window):
        window += news.feed[(feed_pointer+inc)%len(news.feed)]
    oled.fill_rect(0, 0, 127, 10, 0) # white background
    oled.fill_rect(0, 0, 32, 10, 1) # white background
    oled.text(f'NEWS', 0, 2, 0)
    oled.text(f'    {window}', 0, 2, 1)
    
def render (feed_pointer, news_window):

    '''
    Render loop.
    '''
    
    while True:
        
        if news.feed:
            show_news_feed_window(feed_pointer, news_window)
            feed_pointer = (feed_pointer + 1) % len(news.feed)
        oled.show()
        sleep(.3)

# ============= Ticker Code ==============
def tick ():

    '''
    Live crypto ticker implementation with symbol switching button.
    '''
    
    # extract the symbols for reference
    symbol = krakenReference[COIN]
    
    # alter display mode at every cycle
    PAGE = 0

    # conversion
    intervals_per_day = int(1440/INTERVAL)
    intervals_per_hour = int(60/INTERVAL)
    
    # news buffer
    # news_feed = ''
    news_window = 11
    feed_pointer = 0
    
    ticks = 0
    
    # - init render thread -
#     news_feed = load_news_feed()
#     print('news feed', news_feed)
#     show_news_feed_window(news_feed, feed_pointer, news_window)
    _thread.start_new_thread(render, (feed_pointer, news_window))
    sleep(1)

    while True:

        try:
            
            # check every ~5 minutes for news
            if ticks % 20 == 0:
                print(f'request news feed from {github_feed_target}')
                print('news feed', news.feed)
                news.feed = load_news_feed()

            # request closed price array
            closed = krakenApi.history(symbol, INTERVAL, EPOCH, REFERENCE)
            
            # check if the symbol has a significant history first
            if len(closed) < TREND_INTERVALS + 1:
                print_display(f'not enough data for {symbol} yet.')
                return
            
            # extract last price
            price = digits(closed[-1], 5)
            print(f'last price ${price}')
            
            clear()
            
            # ---- page casing ----
            
            # show chart
            if DISPLAY_PAGES[PAGE] == 'chart':

                # compute change for price line only
                change_24h = round(100 * (closed[-1] / closed[-intervals_per_day] - 1), 1)
                sign = ['+', ''][change_24h < 0]
                
                # build price line with 24h return 
                priceLine = f'${price} {sign}{change_24h}%'
                
                # add price line
                oled.text(priceLine, leftPadding, 15)
                
                # plot chart below
                plot_chart (oled, closed, height=32, y=3)

            # show statistics, like price, change, volatility etc.    
            elif DISPLAY_PAGES[PAGE] == 'statistics':
                
                # compute statistics
                d = drift(closed, TREND_INTERVALS)
                d_h = round(100 * d / intervals_per_hour, 2)
                v = volatility(closed, d, TREND_INTERVALS)
                v_h = round(100*v/sqrt(intervals_per_hour),2) # see https://en.wikipedia.org/wiki/Volatility_(finance)#Mathematical_definition
                change_24h = round(100 * (closed[-1] / closed[-intervals_per_day] - 1), 1)
                sign = ['+', ''][change_24h < 0]
                
                # build price line with 24h return 
                priceLine = f'${price} {sign}{change_24h}%'
                
                # build ROI line from 1h drift
                roiLine = f'ROI: {["+", ""][d < 0]}{d_h} %/h'
                
                # build volatility line
                volLine = f'VOL: {v_h} %/h'
                
                # add assembled lines
                oled.text(priceLine, leftPadding , 15)
                oled.text(roiLine, leftPadding , 30)
                oled.text(volLine, leftPadding , 45)
                
                # the oled.show() is called in render thread every second
            
            # delay
            sleep(UPDATE-1)
            
        except Exception as e:

            sys.print_exception(e)

        finally:

            # flip to next page
            PAGE = (PAGE + 1) % len(DISPLAY_PAGES)
            
            # increment ticks
            ticks += 1
            
            sleep(1)
    
            

# ============= Main Sequence ==============
def main ():
    try:
        # delay to get into bootsel button working
        sleep(1)
        
        # show logo
        trademark(3)
        
        # ---- credentials & config ----
        # check if wifi credentials were not set
        if not _config['ssid'] or not _config['wpa2']:
            welcome()
            spawn()
            return
        elif bootsel_is_pressed():
            text('started         captive        portal:         bitboi captive', startLine=0)
            spawn()
            return
        
        # ---- start Wi-Fi connection ---- 
        # wifi has highest priority
        attempts = 3
        wifi.active(True)
        # disable powersave mode to make the wifi more responsive
        wifi.config(pm = 0xa11140)
        center('connecting...', 10, 10, 24, 0.05)
        for _ in range(attempts):
            try:
                wifi.connect(_config['ssid'], _config['wpa2'])
                sleep(1)
                # construct a little test request
                # this should defnitely throw exceptions
                news.feed = load_news_feed()
                # set global flag
                wifi_connected = True
                break
            except OSError as e:
                if str(e) == 'no matching wifi network found':
                    print_display('No network!')
                else:
                    print_display('Connection Error > Reset')
                    sleep(1)
                    reset()
                sys.print_exception(e)
                return -1
            except Exception as e:
                print_display('Unknown error while connecting!')
                sys.print_exception(e)
                return -2
        
        # ---- update pipeline ----
        # auto_update()
        
        # ---- start ticker ----
        center('ticker', 10, 45, 24, 0.1)
        tick()
    except Exception as e:
        sys.print_exception(e)
    finally:
        sys.exit()


if __name__ == '__main__':
    main()

