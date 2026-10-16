import appConfig from '../../app.json';

describe('scaffold', () => {
  it('registers the skillcoach deep-link scheme (FR-013)', () => {
    expect(appConfig.expo.scheme).toBe('skillcoach');
    expect(appConfig.expo.name).toBe('Skill Coach');
  });
});
