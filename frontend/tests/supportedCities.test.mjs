import assert from 'node:assert/strict'
import { test } from 'node:test'
import { SUPPORTED_CITIES, cityInputError, normalizeCityText, resolveSupportedCity, searchSupportedCities } from '../src/data/supportedCities/index.ts'

test('all 80 canonical names and explicit aliases resolve to their source labels', () => {
  assert.equal(SUPPORTED_CITIES.length, 80)
  assert.equal(new Set(SUPPORTED_CITIES.map(c => c.name)).size, 80)
  for (const city of SUPPORTED_CITIES) {
    assert.equal(resolveSupportedCity(city.name), city.name)
    assert.equal(resolveSupportedCity(` ${city.name.toUpperCase()} `), city.name)
    for (const alias of city.aliases) assert.equal(resolveSupportedCity(alias), city.name)
    assert.match(city.country_code, /^[a-z]{2}$/)
  }
})
test('search finds aliases and partial names without accepting partial requests', () => {
  assert.ok(searchSupportedCities('rom').some(c => c.name === 'Rome'))
  assert.equal(resolveSupportedCity('rom'), null)
  assert.deepEqual(searchSupportedCities(' ROMA ').map(c => c.name), ['Rome'])
  assert.deepEqual(searchSupportedCities('Atlantis'), [])
  assert.equal(resolveSupportedCity('Rome, Italy'), null)
})
test('normalization matches adapter whitespace and does not invent accent folding or aliases', () => {
  assert.equal(normalizeCityText(' \tABU\u0085  DHABI\n'), 'abu dhabi')
  assert.equal(resolveSupportedCity(' \tABU\u0085  DHABI\n'), 'Abu Dhabi')
  assert.equal(resolveSupportedCity('İstanbul'), null)
  assert.equal(resolveSupportedCity('\uFEFFRome'), null)
})
test('blank, whitespace, unsupported and oversized inputs have useful errors', () => {
  for (const value of ['', '  ', '\t\n', 'Atlantis', 'x'.repeat(201)]) assert.ok(cityInputError(value))
  assert.match(cityInputError('x'.repeat(201)), /200/)
  assert.equal(cityInputError(' ROMA '), undefined)
})
