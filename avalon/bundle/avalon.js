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
    _id: 0,
    id: function() { return this._id = (this._id + 1) % MAX_ID; },
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

  /**
   * Deterministic JSON stringify
   * @param {object} obj
   * @returns {string}
   */
  avalon.stringify = function stringify(obj) {
    var type = Object.prototype.toString.call(obj);

    // IE8 <= 8 does not have array map
    var map = Array.prototype.map || function map(callback) {
      var ret = [];
      for (var i = 0; i < this.length; i++) {
        ret.push(callback(this[i]));
      }
      return ret;
    };

    if (type === '[object Object]') {
      var pairs = [];
      for (var k in obj) {
        if (!obj.hasOwnProperty(k)) continue;
        pairs.push([k, stringify(obj[k])]);
      }
      pairs.sort(function(a, b) { return a[0] < b[0] ? -1 : 1 });
      pairs = map.call(pairs, function(v) { return '"' + v[0] + '":' + v[1] });
      return '{' + pairs + '}';
    }

    if (type === '[object Array]') {
      return '[' + map.call(obj, function(v) { return stringify(v) }) + ']';
    }

    return JSON.stringify(obj);
  };

  /**
   * Call a server method
   * @param {string} methodName method name
   * @param {Array} args
   * @returns {object} resume generator
   */
  avalon.call = function call(methodName, args) {
    if (!avalon.channel || avalon.channel.readyState !== SockJS.OPEN) {
      throw new RuntimeError('Not connected');
    }
    var id = rpc.id();
    avalon.channel.send(JSON.stringify({
      id: id,
      method: 'rpc',
      params: [methodName, args]
    }));
    return rpc.response[id] = Promise(id);
  };


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
          var subscription = collection.subscriptions[data.query];
          if (!subscription) {
            console.error('Not subscribed to collection: ' +
              data.collection + ' query: ' + data.query);
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
        case 'rpc':
          if (!rpc.response[data.id]) {
            console.error('Unknown rpc response id: ' + data.id);
            break;
          }
          var promise = rpc.response[data.id];
          promise.set_result(data.result);
          schedule(promise);
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
      }, 1000);

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
            params: [collection, subscription.query]
          }));

          subscription.state = 'PENDING';
          (function(subscription) {
            window.setTimeout(function pending() {
              if (subscription.state === 'OPEN') return;
              subscription.state = 'CLOSED';
              avalon.channel.subscribe();
            }, 1000);
          })(subscription);
        }
      }
    };

    channel._send = channel.send;
    channel.send = function send(data) {
      // Use `avalon.channel` rather than `this` because we always want to
      // refer to the currently active channel
      (function send() {
        if (avalon.channel.readyState === SockJS.OPEN) {
          avalon.channel._send(data);
          return
        }
        window.setTimeout(send, 1000);
      })();
    };
  })();


  var Collection = function Collection(collection) {
    this.collection = collection;
    this.subscriptions = {};
  };

  Collection.prototype.subscribe = function subscribe(query) {
    var subscriptions = avalon.model[this.collection].subscriptions;

    // Use deterministic stringify because we want the same query
    // to map to the same subscription result set
    query = avalon.stringify(query || {});
    if (subscriptions[query]) return subscriptions[query];

    var result = [];
    result.index = {};
    subscriptions[query] = {
      result: result,
      query: query,
      state: 'CLOSED'
    };

    avalon.channel.subscribe();
    return result;
  };

  Collection.prototype.update = function update(obj, operations) {
    if (!obj._id) {
      console.error('Object has no _id', obj);
      return;
    }
    avalon.channel.send(JSON.stringify({
      method: 'update',
      params: [this.collection, {_id: obj._id}, operations || {}]
    }))
  };

  var Store = function Store() {};
  Store.prototype = {
    __getattr__: function(self, collection) {
      return this[collection] = new Collection(collection);
    }
  };

  avalon.model = new Store();
})(this)
