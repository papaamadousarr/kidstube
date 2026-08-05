from moviepy.video.fx.CrossFadeIn import CrossFadeIn
from moviepy.video.fx.CrossFadeOut import CrossFadeOut

CROSSFADE_DURATION = 0.4


def with_crossfade(clip, duration: float = CROSSFADE_DURATION):
    return clip.with_effects([CrossFadeIn(duration), CrossFadeOut(duration)])
