import datetime
import enum
import threading
import time
from flask import Flask
from jinja2 import Markup, Environment, FileSystemLoader
from pyecharts.globals import CurrentConfig, ThemeType

# 关于 CurrentConfig，可参考 [基本使用-全局变量]
from logger import logger

CurrentConfig.GLOBAL_ENV = Environment(loader=FileSystemLoader("./templates"))
from pyecharts.commons.utils import JsCode
from pyecharts import options as opts
from pyecharts.charts import Bar
from pynput import mouse, keyboard
from sqlalchemy import *
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import SingletonThreadPool


class Utils(object):
    @staticmethod
    def now():
        return int(time.time())

    @staticmethod
    def get_today0_ts():
        return int(time.mktime(datetime.date.today().timetuple()))

    @staticmethod
    def get_yesterday0_ts():
        return int(
            time.mktime(
                time.strptime(
                    str(datetime.date.today() - datetime.timedelta(days=1)), "%Y-%m-%d"
                )
            )
        )


@enum.unique
class EventRecordType(enum.Enum):
    EventRecordTypeNil = 0
    EventRecordTypeMouse = 1
    EventRecordTypeKeyboard = 2


@enum.unique
class ButtonEventType(enum.Enum):
    ButtonEventTypeNil = 0
    ButtonEventTypeRelease = 1  # 按下
    ButtonEventTypeRoll = 2  # 抬起
    ButtonEventTypeMove = 3  # 移动


base = declarative_base()

engine = create_engine(
    "sqlite:///.db?check_same_thread=false",
    poolclass=SingletonThreadPool,
    pool_size=128,
    pool_recycle=3600,
    pool_pre_ping=True,
)


class EventRecord(base):
    __tablename__ = "event_record"

    id = Column(
        BigInteger, primary_key=True, nullable=True, autoincrement=True, comment="主键"
    )

    event_type = Column(Integer, comment="事件类型", server_default="0")

    event_at = Column(Integer, comment="事件创建时间", server_default=str(Utils.now()))

    button = Column(String, comment="按键", server_default="")

    button_event_type = Column(Integer, comment="进行了什么样子的按键操作", server_default="0")


base.metadata.create_all(engine, )

session = sessionmaker(bind=engine)


def _get_db():
    return session()


class KeyboardMonitor(object):
    def __init__(self):
        self.listener = None
        self.run()

    def run(self):
        # 按下按键
        def on_press(key):
            event = EventRecord(
                event_at=Utils.now(),
                event_type=EventRecordType.EventRecordTypeKeyboard.value,
                button_event_type=ButtonEventType.ButtonEventTypeRoll.value,
            )
            if isinstance(key, keyboard._win32.KeyCode):
                event.button = key.char
            elif isinstance(key, keyboard.Key):
                event.button = key.name
            else:
                print("key: {}, type: {}".format(key, type(key)))

            add_event(event)

        # 释放按键
        def on_release(key):
            event = EventRecord(
                event_at=Utils.now(),
                event_type=EventRecordType.EventRecordTypeKeyboard.value,
                button_event_type=ButtonEventType.ButtonEventTypeRelease.value,
            )

            if isinstance(key, keyboard._win32.KeyCode):
                event.button = key.char
            elif isinstance(key, keyboard.Key):
                event.button = key.name
            else:
                print("key: {}, type: {}".format(key, type(key)))

            add_event(event)

        def listen():
            logger.info("keyboard monitor starting...")
            # 监听键盘按键
            with keyboard.Listener(
                    on_press=on_press, on_release=on_release
            ) as _listener:
                _listener.join()

        if self.listener is None:
            self.listener = threading.Thread(target=listen, daemon=True).start()


class MouseMonitor(object):
    def __init__(self):
        self.listener = None
        self.run()

    def run(self):
        # 移动
        def on_move(x, y):
            pass

        # 点击  button——安装的哪个按键（左击右击）     pressed——是否是按压
        def on_click(x, y, button, pressed):
            event = EventRecord(
                event_at=Utils.now(),
                event_type=EventRecordType.EventRecordTypeMouse.value,
                button_event_type=ButtonEventType.ButtonEventTypeRelease.value,
                button=button.name,
            )

            if pressed:
                event.button_event_type = ButtonEventType.ButtonEventTypeRoll.value
            else:
                event.button_event_type = ButtonEventType.ButtonEventTypeRelease.value

            add_event(event)

        # 滚轮
        def on_scroll(x, y, dx, dy):
            pass
            # print(x, y)

        def listen():
            logger.info("mouse monitor starting...")

            # #监听鼠标
            with mouse.Listener(
                    on_move=on_move, on_click=on_click, on_scroll=on_scroll
            ) as _listener:
                _listener.join()

        if self.listener is None:
            self.listener = threading.Thread(target=listen, daemon=True).start()


MouseMonitor()
KeyboardMonitor()


# app = FastAPI(title="notify", version="0.0.1.10")


def add_event(event: EventRecord):
    _db = _get_db()
    _db.add(event)
    _db.commit()
    # print(event.__dict__)


app = Flask(__name__, static_folder="templates")


def show(x: list, y: list):
    bar = Bar(init_opts=opts.InitOpts(theme=ThemeType.WONDERLAND))
    bar.add_xaxis(x)
    bar.add_yaxis("", y, category_gap="60%")
    bar.set_series_opts(
        itemstyle_opts={
            "normal": {
                "color": JsCode(
                    """new echarts.graphic.LinearGradient(0, 0, 0, 1, [{
                offset: 0,
                color: 'rgba(0, 244, 255, 1)'
            }, {
                offset: 1,
                color: 'rgba(250, 177, 160, 1)'
            }], false)"""
                ),
                "barBorderRadius": [30, 30, 30, 30],
                "shadowColor": "rgb(0, 160, 221)",
            }
        }
    )

    bar.load_javascript()
    bar.render_notebook()

    return Markup(bar.render_embed())


@app.route("/yesterday")
def yesterday():
    x = []
    y = []

    sql = "select count(*), button from event_record where {} <= event_at and event_at < {} and event_type = 2 group by button,event_type order by button".format(
        Utils.get_yesterday0_ts(), Utils.get_today0_ts()
    )
    result = _get_db().execute(sql).fetchall()

    for record in result:
        x.append(record[1])
        y.append(record[0])

    return show(x, y)


@app.route("/")
@app.route("/today")
def today():
    x = []
    y = []

    sql = "select count(*), button from event_record where event_at > {} and event_type = 2 group by button,event_type order by button".format(
        Utils.get_yesterday0_ts(), Utils.get_today0_ts()
    )
    result = _get_db().execute(sql).fetchall()

    for record in result:
        x.append(record[1])
        y.append(record[0])

    return show(x, y)


@app.route("/")
def index():
    x = []
    y = []

    sql = "select count(*), button from event_record where event_type = 2 group by button,event_type order by button"
    result = _get_db().execute(sql).fetchall()

    for record in result:
        x.append(record[1])
        y.append(record[0])

    return show(x, y)


if __name__ == "__main__":
    app.run(debug=True)
