// This should run after the video elements are available
//    adds back audio to v.redd.it videos when possible

for (vid of document.getElementsByClassName("video")) {
    // If the video is from reddit then they seperated the audio into a seperate file
    //   annoying, but we can hack an audio element in and trigger it to play to workaround it
    const vidSrc = vid.getElementsByTagName("source")[0].src;
    if ( vidSrc.match('https://v.redd.it') ) {
        const sound    = document.createElement('audio');
        sound.src      = vidSrc.replace(/DASH_\d+\.mp4/ , 'DASH_audio.mp4');
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
