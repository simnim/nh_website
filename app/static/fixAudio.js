// This should run after the video elements are available
//    adds back audio to v.redd.it videos when possible

async function fixAudio(vid) {
    // If the video is from reddit then they seperated the audio into a seperate file
    //   annoying, but we can hack an audio element in and trigger it to play to workaround it
    const source = vid.getElementsByTagName("source")[0];
    if (!source || !source.src || !source.src.match('https://v.redd.it')) {
        return;
    }
    const vidSrc = source.src;

    let DASHPlaylistText;
    try {
        const DASHplaylist = await fetch(vidSrc.replace(/DASH_\d+\.mp4/, "DASHPlaylist.mpd"));
        if (!DASHplaylist.ok) {
            return;
        }
        DASHPlaylistText = await DASHplaylist.text();
    } catch (err) {
        return;
    }

    // why parse when you can just matchAll?
    const audio_q_regexp = /DASH_AUDIO_(.*?).mp4/g;
    const audio_qs = Array.from(DASHPlaylistText.matchAll(audio_q_regexp));

    const sound_qualities = audio_qs.map(function(element){ return parseInt(element[1]); });
    const use_quality = Math.max(...sound_qualities);

    // if no quality-specific audio track was found, fall back to a plain "audio" file
    const audioFileName = sound_qualities.length === 0 ? 'audio' : "AUDIO_" + use_quality;

    const sound = document.createElement('audio');
    sound.src = vidSrc.replace(/DASH_\d+\.mp4/, "DASH_" + audioFileName + ".mp4");
    vid.appendChild(sound);

    vid.onplay = function(){
        this.lastChild.play();
        this.lastChild.currentTime = this.currentTime;
    }

    vid.onpause = function(){
        this.lastChild.pause();
    }
}

for (const vid of document.getElementsByTagName("video")) {
    fixAudio(vid);
}
