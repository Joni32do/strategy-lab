/* ============ Skins registry ============
   DOM-free registry of skin descriptors. Safe to load under node.
   Public API (window.Skins / module.exports):
     register(skin)  register a skin; requires skin.id + skin.name (strings);
                     re-registering the same id replaces the existing entry.
     get(id)         -> skin object or undefined.
     list()          -> [{id,name}, ...] in registration order.
     has(id)         -> boolean.
*/
(function () {
  var g = (typeof window !== 'undefined') ? window : global;

  var skins = []; // registration order

  function register(skin) {
    if (!skin || typeof skin.id !== 'string' || typeof skin.name !== 'string') {
      throw new Error('Skins.register: skin must have string id and name');
    }
    var idx = skins.findIndex(function (s) { return s.id === skin.id; });
    if (idx >= 0) { skins[idx] = skin; } // dedupe: replace in place
    else { skins.push(skin); }
    return skin;
  }

  function get(id) {
    return skins.find(function (s) { return s.id === id; });
  }

  function list() {
    return skins.map(function (s) { return { id: s.id, name: s.name }; });
  }

  function has(id) {
    return !!get(id);
  }

  g.Skins = { register: register, get: get, list: list, has: has };

  if (typeof module !== 'undefined') { module.exports = g.Skins; }
})();
