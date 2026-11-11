// Cambodia wall-clock fields, independent of the browser timezone.
(function () {
    const formatter = new Intl.DateTimeFormat('en-GB', {timeZone:'Asia/Phnom_Penh', year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit', hourCycle:'h23'});
    function parts(instant) {
        const result = {};
        formatter.formatToParts(instant || new Date()).forEach(function (p) { if (p.type !== 'literal') result[p.type] = Number(p.value); });
        return result;
    }
    window.NocTime = {parts:parts};
})();
