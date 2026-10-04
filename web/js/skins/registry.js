/* Available skins. To add one: subclass Skin, add tokens to css/skins.css,
 * list the class here. */

import { LabSkin } from './lab.js';
import { PaperSkin } from './paper.js';
import { MinimalSkin } from './minimal.js';

export const SKINS = [LabSkin, PaperSkin, MinimalSkin];

let active = new LabSkin();

export function setSkin(id) {
  const Cls = SKINS.find((s) => s.id === id) || LabSkin;
  active = new Cls();
  active.apply();
  return active;
}

export function skin() { return active; }
