// This should run after the video elements are available
//    adds back audio to v.redd.it videos when possible

for (var vid of document.getElementsByTagName("video")) {
    // If the video is from reddit then they seperated the audio into a seperate file
    //   annoying, but we can hack an audio element in and trigger it to play to workaround it
    const vidSrc = vid.getElementsByTagName("source")[0].src;
    if ( vidSrc.match('https://v.redd.it') ) {
        // const DASHplaylist = await fetch('https://v.redd.it/wb3fb1mdw9ac1/DASHPlaylist.mpd');
        const DASHplaylist = await fetch(vidSrc.replace(/DASH_\d+\.mp4/ , "DASHPlaylist.mpd"));
        const DASHPlaylistText = await DASHplaylist.text();

        const audio_q_regexp = /DASH_AUDIO_(.*?).mp4/g;
        const audio_qs = Array.from(DASHPlaylistText.matchAll(audio_q_regexp));

        const sound_qualities = audio_qs.map(function(element){ return parseInt(element[1]); });
        const use_quality = Math.max(...sound_qualities);

        const sound = document.createElement('audio');
        const replaceWith = sound_qualities.length===0 ? 'audio' : "AUDIO_"+use_quality;
        // console.log(replaceWith);
        sound.src = vidSrc.replace(/DASH_\d+\.mp4/ , "DASH_"+replaceWith+".mp4");
        vid.parentElement.appendChild(sound);

        // https://stackoverflow.com/questions/6433900/syncing-html5-video-with-audio-playback
        vid.onplay = function(){
            sound.currentTime = vid.currentTime;
            sound.play();
        }

        vid.onpause = function(){
            sound.pause();
        }

    }
}
