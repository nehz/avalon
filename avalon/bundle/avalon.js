/**
 * Avalon client library
 * Copyright 2013, Hybrid Labs
 * License: MIT
 */

(function(globals) {
  'use strict';
  var VERSION = [0, 0, 1];
  var avalon = globals.avalon = {version: VERSION};

  if (window.chrome) {
    console.log(
      '%c  %c  %c  ' +
      '%c  Avalon v' + VERSION.join('.') + '  ' +
      '%c  %c  %c  ',
      'background: #A8DBA8',
      'background: #79BD9A',
      'background: #3B8686',
      'background: #0C0F66; color: white;',
      'background: #3B8686',
      'background: #79BD9A',
      'background: #A8DBA8'
    );
  }
  else {
    console.log('Avalon v' + VERSION.join('.'));
  }


  (function connect() {
    var channel = avalon.channel = new SockJS('/_avalon');

    channel.onopen = function() {
      console.log('Channel connected...');
      // TODO: Resubscribe to any subscriptions
    };

    channel.onmessage = function(e) {
      console.log('message', e.data);
    };

    channel.onclose = function() {
      console.error('Channel connection lost, reconnecting...');
      window.setTimeout(function() {
        connect();
      });
    };
  })();
})(this)
