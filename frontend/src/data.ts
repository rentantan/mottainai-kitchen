import type { Category, PantryItem, Recipe } from './types'

export const STORAGE_KEY = 'mottainai-kitchen-pantry-v1'
export const AUTH_TOKEN_KEY = 'mottainai-kitchen-auth-token-v1'
export const AUTH_EMAIL_KEY = 'mottainai-kitchen-auth-email-v1'
export const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
export const categoryOptions: Category[] = ['野菜・果物', '肉・魚', '乳製品・卵', '主食・麺', '調味料', 'その他']
export const categoryEmoji: Record<Category, string> = {
  '野菜・果物': '🥬', '肉・魚': '🥩', '乳製品・卵': '🥚', '主食・麺': '🍚', '調味料': '🧂', 'その他': '🛒',
}

export const demoItems: PantryItem[] = [
  { id: 'demo-1', name: '牛乳', quantity: 1, unit: '本', expiryDate: dateOffset(1), category: '乳製品・卵', emoji: '🥛', note: '開封済み', createdAt: new Date().toISOString() },
  { id: 'demo-2', name: '卵', quantity: 6, unit: '個', expiryDate: dateOffset(3), category: '乳製品・卵', emoji: '🥚', note: '', createdAt: new Date().toISOString() },
  { id: 'demo-3', name: 'ほうれん草', quantity: 1, unit: '袋', expiryDate: dateOffset(0), category: '野菜・果物', emoji: '🥬', note: '', createdAt: new Date().toISOString() },
  { id: 'demo-4', name: '鶏もも肉', quantity: 250, unit: 'g', expiryDate: dateOffset(2), category: '肉・魚', emoji: '🍗', note: '冷蔵', createdAt: new Date().toISOString() },
  { id: 'demo-5', name: 'にんじん', quantity: 2, unit: '本', expiryDate: dateOffset(7), category: '野菜・果物', emoji: '🥕', note: '', createdAt: new Date().toISOString() },
  { id: 'demo-6', name: '食パン', quantity: 4, unit: '枚', expiryDate: dateOffset(-1), category: '主食・麺', emoji: '🍞', note: '', createdAt: new Date().toISOString() },
  { id: 'demo-7', name: 'ミニトマト', quantity: 1, unit: 'パック', expiryDate: dateOffset(5), category: '野菜・果物', emoji: '🍅', note: '', createdAt: new Date().toISOString() },
  { id: 'demo-8', name: '豆腐', quantity: 1, unit: '丁', expiryDate: dateOffset(1), category: 'その他', emoji: '⬜', note: '', createdAt: new Date().toISOString() },
]

export function dateOffset(days: number) {
  const date = new Date()
  date.setDate(date.getDate() + days)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
/** Offline copy of backend FALLBACK_RECIPES (backend/recipes.py). Keep both lists in sync. */
export const fallbackRecipes: Omit<Recipe, 'matchedIngredients' | 'missingIngredients' | 'usesExpiring' | 'matchPercent'>[] = [
  { id: 'egg-fried-rice', name: '卵だけでも満足チャーハン', description: 'ごはんと卵があれば作れる、洗い物少なめの定番ごはん。', minutes: 8, difficulty: 'かんたん', emoji: '🍳', ingredients: ['ごはん', '卵', 'しょうゆ'], ingredientDetails: ['ごはん 茶碗1杯', '卵 1個', 'しょうゆ 小さじ1'], estimatedCostYen: 100, servings: 1, steps: ['卵を溶き、フライパンに油をひいて卵に火が通るまで炒める。', 'ごはんを加えてほぐしながら炒める。', 'しょうゆを鍋肌から回し入れて全体を混ぜる。'] },
  { id: 'tofu-don', name: '豆腐のそぼろ風どんぶり', description: 'ひき肉なしでもボリュームが出る、節約向けの一皿。', minutes: 12, difficulty: 'かんたん', emoji: '🍚', ingredients: ['ごはん', '豆腐', 'しょうゆ', '砂糖'], ingredientDetails: ['ごはん 茶碗1杯', '豆腐 1/2丁', 'しょうゆ 大さじ1', '砂糖 小さじ1'], estimatedCostYen: 150, servings: 1, steps: ['豆腐はキッチンペーパーで軽く水気を取る。', 'フライパンで豆腐を崩しながら炒め、水分を飛ばす。', 'しょうゆと砂糖を加えてなじませ、ごはんにのせる。'] },
  { id: 'cabbage-egg', name: 'キャベツと卵のふんわり炒め', description: '余り野菜を使い切りやすい、フライパンひとつの簡単おかず。', minutes: 10, difficulty: 'かんたん', emoji: '🥬', ingredients: ['キャベツ', '卵', '塩こしょう'], ingredientDetails: ['キャベツ 2枚', '卵 1個', '塩こしょう 少々'], estimatedCostYen: 120, servings: 1, steps: ['キャベツを食べやすい大きさにちぎる。', 'フライパンでキャベツを炒め、しんなりしたら溶き卵を加える。', '卵にしっかり火が通るまで混ぜ、塩こしょうで味を調える。'] },
  { id: 'butter-soy-pasta', name: 'きのこのバターしょうゆパスタ', description: 'パスタときのこで作る、材料少なめの一人ごはん。', minutes: 15, difficulty: 'かんたん', emoji: '🍝', ingredients: ['パスタ', 'しめじ', 'しょうゆ', 'バター'], ingredientDetails: ['パスタ 80g', 'しめじ 1/3パック', 'しょうゆ 小さじ2', 'バター 5g'], estimatedCostYen: 220, servings: 1, steps: ['パスタを袋の表示どおりにゆでる。', 'フライパンでしめじを炒め、ゆでたパスタを加える。', 'しょうゆとバターを加えて全体を混ぜる。'] },
  { id: 'tuna-mayo-rice', name: 'ツナマヨたまご丼', description: '火を使う工程を少なくしたい日に。ツナ缶を活用。', minutes: 7, difficulty: 'かんたん', emoji: '🥫', ingredients: ['ごはん', 'ツナ缶', '卵', 'マヨネーズ'], ingredientDetails: ['ごはん 茶碗1杯', 'ツナ缶 1/2缶', '卵 1個', 'マヨネーズ 小さじ1'], estimatedCostYen: 230, servings: 1, steps: ['ツナ缶の油を軽く切り、マヨネーズと混ぜる。', '卵は黄身と白身にしっかり火が通るまで加熱する。', 'ごはんにツナマヨと卵をのせる。'] },
  { id: 'spinach-egg', name: 'ほうれん草と卵のしょうゆ炒め', description: '傷みやすい葉物を一気に使い切れる、フライパンひとつの副菜。', minutes: 8, difficulty: 'かんたん', emoji: '🥬', ingredients: ['ほうれん草', '卵', 'しょうゆ'], ingredientDetails: ['ほうれん草 1/2袋', '卵 1個', 'しょうゆ 小さじ1'], estimatedCostYen: 130, servings: 1, steps: ['ほうれん草を洗い、4cm長さに切る。', 'フライパンに油をひき、ほうれん草を茎から炒める。', '溶き卵を加え、卵にしっかり火が通るまで混ぜながら炒める。', 'しょうゆを回し入れて全体になじませる。'] },
  { id: 'spinach-milk-pasta', name: 'ほうれん草のミルクスープパスタ', description: '牛乳とコンソメで作る、生クリームなしのやさしいスープパスタ。', minutes: 15, difficulty: 'かんたん', emoji: '🍝', ingredients: ['パスタ', 'ほうれん草', '牛乳', 'コンソメ'], ingredientDetails: ['パスタ 80g', 'ほうれん草 1/4袋', '牛乳 150ml', 'コンソメ 小さじ1'], estimatedCostYen: 200, servings: 1, steps: ['鍋に水200mlとコンソメを入れて沸かし、半分に折ったパスタを入れる。', '袋の表示時間どおりに混ぜながら煮る。', 'ゆで上がり2分前に、4cmに切ったほうれん草を加える。', '牛乳を加えて弱火で温め、沸騰させないように仕上げる。'] },
  { id: 'teriyaki-chicken-don', name: '鶏肉の照り焼き丼', description: '甘辛だれでごはんが進む、ボリューム満点の一人丼。', minutes: 15, difficulty: 'ふつう', emoji: '🍗', ingredients: ['ごはん', '鶏肉', 'しょうゆ', '砂糖'], ingredientDetails: ['ごはん 茶碗1杯', '鶏肉 120g', 'しょうゆ 大さじ1', '砂糖 大さじ1/2'], estimatedCostYen: 260, servings: 1, steps: ['鶏肉はひと口大に切る。', 'フライパンで皮目から焼き、ふたをして弱めの中火で中まで火を通す。', '切り口が白くなったら、しょうゆと砂糖を加えて煮からめる。', 'ごはんにのせ、たれをかける。'] },
  { id: 'moyashi-pork-steam', name: 'もやしと豚肉のレンジ蒸し', description: '火を使わず電子レンジで完成。洗い物は耐熱皿だけ。', minutes: 10, difficulty: 'かんたん', emoji: '🥢', ingredients: ['もやし', '豚肉', 'ポン酢'], ingredientDetails: ['もやし 1袋', '豚肉 80g', 'ポン酢 大さじ1'], estimatedCostYen: 200, servings: 1, steps: ['耐熱皿にもやしを広げ、豚肉を重ならないようにのせる。', 'ふんわりラップをして、600Wで4〜5分加熱する。', '豚肉の赤い部分がなくなったか確認し、足りなければ30秒ずつ追加加熱する。', 'ポン酢をかけていただく。'] },
  { id: 'carrot-kinpira', name: 'にんじんのきんぴら', description: 'にんじん1本を作り置きおかずに。お弁当にも使える。', minutes: 10, difficulty: 'かんたん', emoji: '🥕', ingredients: ['にんじん', 'しょうゆ', '砂糖', 'ごま油'], ingredientDetails: ['にんじん 1/2本', 'しょうゆ 小さじ2', '砂糖 小さじ1', 'ごま油 小さじ1'], estimatedCostYen: 60, servings: 1, steps: ['にんじんを細切りにする。', 'フライパンにごま油を熱し、にんじんがしんなりするまで炒める。', 'しょうゆと砂糖を加え、汁気がなくなるまで炒める。'] },
  { id: 'tomato-egg-soup', name: 'トマトと卵のスープ', description: 'あと一品ほしいときに。トマトの酸味で食欲がない日にも。', minutes: 8, difficulty: 'かんたん', emoji: '🍅', ingredients: ['トマト', '卵', 'コンソメ'], ingredientDetails: ['ミニトマト 5個', '卵 1個', 'コンソメ 小さじ1'], estimatedCostYen: 120, servings: 1, steps: ['ミニトマトを半分に切る。', '小鍋に水200mlとコンソメを入れて沸かし、トマトを入れて1分煮る。', '溶き卵を回し入れ、卵がふんわり固まるまでしっかり加熱する。'] },
  { id: 'natto-egg-udon', name: '納豆たまごうどん', description: '冷凍うどんで10分。たんぱく質もとれる忙しい日の味方。', minutes: 10, difficulty: 'かんたん', emoji: '🍜', ingredients: ['うどん', '納豆', '卵', 'めんつゆ'], ingredientDetails: ['うどん 1玉', '納豆 1パック', '卵 1個', 'めんつゆ 大さじ2'], estimatedCostYen: 170, servings: 1, steps: ['うどんを袋の表示どおりに電子レンジで加熱する。', 'フライパンで目玉焼きを作り、ふたをして黄身まで火を通す。', 'うどんにめんつゆをかけ、納豆と卵をのせて混ぜる。'] },
]
