/**
 * Avalon client library
 * Copyright 2013, Hybrid Labs
 * License: MIT
 */

(function(globals) {
  'use strict';
  var VERSION = [0, 0, 1];
  var MAX_ID = 4294967295;

  var avalon = globals.avalon = {version: VERSION};
  var rpc = {
    id: 0,
    response: {}
  };

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

  function rpc_id() {
    return rpc.id = (rpc.id + 1) % MAX_ID;
  }


  (function connect() {
    var channel = avalon.channel = new SockJS('/_avalon');

    channel.onopen = function() {
      console.log('Channel connected...');
      channel.subscribe();
    };

    channel.onmessage = function(e) {
      var data = JSON.parse(e.data);
      console.log(data);
      switch(data.response) {
        case 'subscribe':
          var collection = avalon.model[data.collection] || {};
          if (data.id && collection.subscriptions) {
            var subscription = collection.subscriptions[data.id];
            if (!subscription) {
              console.warn('Cannot find response id: ' + data.id);
            }
            else if (data.id !== data.subscription_id) {
              delete collection.subscriptions[data.id];
              collection.subscriptions[data.subscription_id] = subscription;
              collection.queries[subscription.query] = data.subscription_id;
            }
          }

          var subscription = collection.subscriptions[data.subscription_id];
          if (!subscription) {
            console.error('Not subscribed to collection: ' +
              data.collection + ' subscription: ' + data.subscription_id);
            return;
          }

          for (var i = 0; i < data.result.length; i++) {
            var doc = data.result[i];
            var _id = doc._id.$oid || doc._id;
            var index = subscription.result.index[_id];
            if (index !== undefined) {
              subscription.result[index] = doc;
            }
            else {
              index = subscription.result.push(doc) - 1;
              subscription.result.index[_id] = index;
            }
          }

          (function apply() {
            if (!avalon.scope) {
              window.setTimeout(apply, 1000);
              return;
            }
            avalon.scope.$apply();
          })();

          subscription.state = 'OPEN';
          break;
        default:
          console.error('Unknown response: ' + data.response);
          break;
      }
    };

    channel.onclose = function() {
      console.error('Channel connection lost, reconnecting...');
      window.setTimeout(function() {
        connect();
      });

      for (var collection in avalon.model) {
        if (!avalon.model.hasOwnProperty(collection)) continue;
        var subscriptions = avalon.model[collection].subscriptions;
        for (var sub_id in subscriptions) {
          if (!subscriptions.hasOwnProperty(sub_id)) continue;
          subscriptions[sub_id].state = 'CLOSED';
        }
      }
    };

    channel.subscribe = function subscribe() {
      if (this.readyState !== SockJS.OPEN) return;

      for (var collection in avalon.model) {
        if (!avalon.model.hasOwnProperty(collection)) continue;
        var subscriptions = avalon.model[collection].subscriptions;

        for (var sub_id in subscriptions) {
          if (!subscriptions.hasOwnProperty(sub_id)) continue;

          var subscription = subscriptions[sub_id];
          if (subscription.state != 'CLOSED') continue;

          this.send(JSON.stringify({
            method: 'subscribe',
            params: [sub_id, collection, JSON.parse(subscription.query)]
          }));

          subscription.state = 'PENDING';
          (function(subscription) {
            window.setTimeout(function pending() {
              if (subscription.state === 'OPEN') return;
              subscription.state = 'CLOSED';
              channel.subscribe();
            }, 10000);
          })(subscription);
        }
      }
    };
  })();


  var Collection = function Collection(collection) {
    this.collection = collection;
    this.subscriptions = {};
    this.queries = {};
  };

  Collection.prototype.subscribe = function subscribe(query) {
    var subscriptions = avalon.model[this.collection].subscriptions;
    var queries = avalon.model[this.collection].queries;

    query = JSON.stringify(query || {});
    if (queries[query]) return subscriptions[query[queries]];

    var result = [];
    var id = rpc_id();
    result.index = {};
    subscriptions[id] = {
      result: result,
      query: query,
      state: 'CLOSED'
    };

    avalon.channel.subscribe();
    return result;
  };

  var Store = function Store() {};
  Store.prototype = {
    __getattr__: function(self, collection) {
      return this[collection] = new Collection(collection);
    }
  };

  avalon.model = new Store();
})(this)
