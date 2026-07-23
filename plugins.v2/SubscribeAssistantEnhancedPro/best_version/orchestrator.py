"""洗版全流程编排：按配置创建洗版订阅。"""
from typing import Callable, Optional

from app.log import logger
from app.schemas.types import MediaType

from ..shared.subscribe import (
    format_subscribe_desc,
    is_full_best_version_subscribe,
    is_tv_episode_best_version_subscribe,
    resolve_subscribe_media_type,
)
from .priority import PriorityManager


class BestVersionOrchestrator:
    """洗版全流程编排器，负责按配置创建洗版订阅。"""

    def __init__(self, priority_manager: PriorityManager,
                 subscribe_oper=None,
                 send_subscribe_added_fn: Optional[Callable] = None,
                 notify_fn: Optional[Callable] = None,
                 related_downloads_fn: Optional[Callable] = None,
                 notification_image_fn: Optional[Callable] = None,
                 plugin_name: str = "订阅助手（增强版）",
                 best_version_type: str = "off",
                 movie_downloader: str = "",
                 tv_downloader: str = "",
                 tv_episode_downloader: str = ""):
        """注入洗版编排依赖。

        best_version_type 控制自动洗版适用范围：
        off=关闭, movie=仅电影, tv=仅剧集, all=电影和剧集。
        类型化下载器独立配置，不受 best_version_type 影响。
        """
        self._priority = priority_manager
        self._subscribe_oper = subscribe_oper
        self._send_subscribe_added = send_subscribe_added_fn
        self._notify = notify_fn
        self._related_downloads = related_downloads_fn
        self._notification_image = notification_image_fn
        self._plugin_name = plugin_name
        self._best_version_type = best_version_type
        self._movie_downloader = movie_downloader
        self._tv_downloader = tv_downloader
        self._tv_episode_downloader = tv_episode_downloader

    def build_payload(self, subscribe) -> dict:
        """构建洗版订阅 payload，保留 episode_group。"""
        payload = {
            "name": subscribe.name,
            "tmdbid": subscribe.tmdbid,
            "season": subscribe.season,
            "episode_group": subscribe.episode_group,
            "save_path": subscribe.save_path,
            "sites": subscribe.sites,
            "filter": subscribe.filter,
            "filter_groups": subscribe.filter_groups,
        }
        payload = {key: value for key, value in payload.items() if value is not None}
        payload["best_version"] = 1
        payload["manual_total_episode"] = 0
        return payload

    def start_best_version(self, subscribe, mediainfo):
        """普通订阅完成后按 best_version_type 开关自动创建洗版订阅。

        由 best_version_type 控制适用范围，类型化下载器为对应类型洗版订阅指定下载器：
        - best_version_type=off → 跳过
        - best_version_type=movie / tv / all → 按媒体类型决定是否创建
        - 创建时从 movie_downloader / tv_downloader 取对应的下载器
        """
        if not self._subscribe_oper or not mediainfo:
            return None
        if subscribe.best_version:
            return None
        media_type = resolve_subscribe_media_type(subscribe)
        if not self._should_create(media_type):
            return None
        is_movie = media_type == MediaType.MOVIE
        if is_movie and self._movie_current_priority(subscribe) >= 100:
            logger.info(
                f"洗版编排：{format_subscribe_desc(subscribe)} "
                f"普通订阅完成资源已达顶档，跳过自动创建洗版订阅"
            )
            if self._notify:
                self._notify(
                    f"{format_subscribe_desc(subscribe)} 已达顶档，跳过洗版订阅",
                    image=self._resolve_notification_image(subscribe, mediainfo),
                    link="#/subscribe/movie?tab=mysub",
                )
            return None
        payload = {
            "best_version": 1,
            "season": subscribe.season,
            "episode_group": subscribe.episode_group,
            "save_path": subscribe.save_path,
            "sites": subscribe.sites,
            "filter": subscribe.filter,
            "filter_groups": subscribe.filter_groups,
        }
        # 按媒体类型选择对应的类型化下载器
        type_downloader = self._resolve_downloader(media_type)
        if type_downloader:
            payload["downloader"] = type_downloader
        # 普通剧集订阅完成后直接进入洗版，才能在新资源下载前执行整季既有版本清理。
        if not is_movie:
            payload["best_version_full"] = 1
        else:
            payload["current_priority"] = self._movie_current_priority(subscribe)
        payload = {key: value for key, value in payload.items() if value is not None}
        # 插件创建的订阅始终重新跟随 TMDB 总集数，不继承已完成订阅的手动锁定状态。
        payload["manual_total_episode"] = 0
        sid, err_msg = self._subscribe_oper.add(mediainfo=mediainfo, **payload)
        if sid:
            mode_label = "洗版"
            logger.info(
                f"洗版编排：{format_subscribe_desc(subscribe)} "
                f"原因=订阅完成，处理=已创建{mode_label}订阅（id={sid}）"
            )
            if self._send_subscribe_added:
                self._send_subscribe_added(sid, mediainfo, username=self._plugin_name)
            if self._notify:
                self._notify(
                    f"{format_subscribe_desc(subscribe)} 已添加{mode_label}订阅",
                    score=mediainfo.vote_average,
                    image=self._resolve_notification_image(subscribe, mediainfo),
                    link="#/subscribe/movie?tab=mysub" if is_movie else "#/subscribe/tv?tab=mysub",
                )
        elif self._notify:
            logger.error(
                f"洗版编排：{format_subscribe_desc(subscribe)} "
                f"原因=添加洗版订阅失败，处理=请检查订阅创建错误，错误={err_msg}"
            )
            self._notify(
                f"{format_subscribe_desc(subscribe)} 添加洗版订阅失败",
                reason=err_msg,
                follow_up="请检查订阅创建错误",
                diagnostic=True,
                image=self._resolve_notification_image(subscribe, mediainfo),
            )
        return sid

    def _resolve_notification_image(self, subscribe, mediainfo):
        """解析洗版通知图片；未注入统一解析器时沿用媒体图片。"""
        if self._notification_image:
            return self._notification_image(subscribe, mediainfo)
        return mediainfo.get_message_image()

    @staticmethod
    def _mode_label(subscribe) -> str:
        """按订阅实际洗版形态返回用户可见标签。"""
        if is_full_best_version_subscribe(subscribe):
            return "洗版"
        if is_tv_episode_best_version_subscribe(subscribe):
            return "分集洗版"
        return ""

    @staticmethod
    def _movie_current_priority(subscribe) -> int:
        """读取电影订阅当前质量优先级，空值按未建立质量基线处理。"""
        try:
            return int(subscribe.current_priority or 0)
        except (TypeError, ValueError):
            return 0

    def _should_create(self, media_type: MediaType) -> bool:
        """洗版类型开关：按 best_version_type 配置决定是否创建洗版订阅。"""
        bt = self._best_version_type
        if bt == "off" or media_type == MediaType.UNKNOWN:
            return False
        if bt == "all":
            return True
        if bt == "movie":
            return media_type == MediaType.MOVIE
        if bt == "tv":
            return media_type == MediaType.TV
        return False

    def _resolve_downloader(self, media_type: MediaType, is_full: bool = True) -> str:
        """根据媒体类型和全集/分集返回对应的类型化下载器。"""
        if media_type == MediaType.MOVIE:
            return self._movie_downloader
        if media_type == MediaType.TV:
            return self._tv_downloader if is_full else self._tv_episode_downloader
        return ""
