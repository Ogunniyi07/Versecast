import unittest
from scripture_refs import KJV, words_to_digits


class SpokenReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kjv = KJV()

    def labels(self, text):
        return [r.label() for r in self.kjv.find(text)]

    def test_digit_references(self):
        self.assertEqual(self.labels("Turn with me to John 3:16."), ["John 3:16"])
        self.assertEqual(self.labels("Romans 8:28-30"), ["Romans 8:28-30"])
        self.assertEqual(self.labels("Song of Solomon 2:4"), ["Song of Solomon 2:4"])

    def test_spoken_words(self):
        self.assertEqual(self.labels("John chapter three verse sixteen"), ["John 3:16"])
        self.assertEqual(self.labels("First Corinthians chapter thirteen verse four"), ["1 Corinthians 13:4"])
        self.assertEqual(self.labels("Psalm twenty three verse one"), ["Psalms 23:1"])
        self.assertEqual(self.labels("Psalms one hundred nineteen verse one hundred five"), ["Psalms 119:105"])

    def test_ranges(self):
        self.assertEqual(self.labels("1 Corinthians 13 verses 4 to 7"), ["1 Corinthians 13:4-7"])
        self.assertEqual(self.labels("John 3:16 and 17"), ["John 3:16-17"])
        self.assertEqual(self.labels("John 3:16 to 4:2"), ["John 3:16-4:2"])

    def test_single_chapter_books(self):
        self.assertEqual(self.labels("Jude 3"), ["Jude 1:3"])
        self.assertEqual(self.labels("2 John 4"), ["2 John 1:4"])

    def test_verse_text_matches_kjv(self):
        ref = self.kjv.find("John 3:16")[0]
        rows = self.kjv.verse_texts(ref)
        self.assertEqual(rows[0][0:2], (3, 16))
        self.assertTrue(rows[0][2].startswith("For God so loved the world"))

    def test_invalid_references_rejected(self):
        self.assertEqual(self.labels("Genesis 99:1"), [])        # no chapter 99
        self.assertEqual(self.labels("John 3:99"), [])           # no verse 99
        self.assertEqual(self.labels("John 3:16-2"), [])         # reversed range

    def test_chapter_only_shows_whole_chapter(self):
        self.assertEqual(self.labels("That's our story for Matthew 2."), ["Matthew 2:1-23"])
        self.assertEqual(self.labels("Matthew chapter two"), ["Matthew 2:1-23"])
        self.assertEqual(self.labels("Psalm 23 is my favourite"), ["Psalms 23:1-6"])
        self.assertEqual(self.labels("Genesis fifty-one"), [])    # no chapter 51
        # Written as digits, "51" is how Whisper writes a spoken "five one".
        self.assertEqual(self.labels("Genesis 51"), ["Genesis 5:1"])
        self.assertEqual(self.labels("Jude 3"), ["Jude 1:3"])     # one-chapter book: still a verse

    def test_chapter_ranges(self):
        self.assertEqual(self.labels("Genesis 1 to 2"), ["Genesis 1:1-2:25"])
        self.assertEqual(self.labels("Read Romans chapters five to six"), ["Romans 5:1-6:23"])
        self.assertEqual(self.labels("Genesis 1 through 3"), ["Genesis 1:1-3:24"])
        self.assertEqual(self.labels("John 3:16 and 17"), ["John 3:16-17"])   # colon: still verses
        self.assertEqual(self.labels("Jude 3 and 4"), ["Jude 1:3-4"])         # one-chapter book: verses
        self.assertEqual(self.labels("Genesis 2 to 1"), [])                   # backwards
        self.assertEqual(self.labels("Genesis 50 to 51"), [])                 # no chapter 51
        self.assertEqual(self.labels("Acts 2 to 3 weeks ago"), [])            # counting
        self.assertEqual(self.labels("Genesis chapter one and verse two"), ["Genesis 1:2"])
        self.assertEqual(self.labels("Genesis chapter one, verse two"), ["Genesis 1:2"])

    def test_verse_to_end_of_chapter(self):
        self.assertEqual(self.labels("Psalm 119 verse 1 to the end."), ["Psalms 119:1-176"])
        self.assertEqual(self.labels("John 3 from verse sixteen till the end"), ["John 3:16-36"])
        self.assertEqual(self.labels("Romans 8:28 through the end"), ["Romans 8:28-39"])
        self.assertEqual(self.labels("John 3:16 to the end of the service"), ["John 3:16-36"])

    def test_verse_text_has_clean_punctuation(self):
        rows = self.kjv.verse_texts(self.kjv.find("Genesis 4:1")[0])
        self.assertTrue(rows[0][2].endswith("from the LORD."))

    def test_saying_chapter_overrides_counting_guard(self):
        text = ("Because I want you to be able to catch my attention in the book of Genesis "
                "chapter 1 of this book and also in the book of Jeremiah chapter 5 of this book.")
        self.assertEqual(self.labels(text), ["Genesis 1:1-31", "Jeremiah 5:1-31"])
        self.assertEqual(self.labels("Acts chapter 2 weeks ago we read"), ["Acts 2:1-47"])
        self.assertEqual(self.labels("Jude chapter 1"), ["Jude 1:1-25"])
        self.assertEqual(self.labels("Genesis 1 of this book"), ["Genesis 1:1-31"])

    def test_misheard_verse_word(self):
        self.assertEqual(self.labels("John chapter 5 best one"), ["John 5:1"])
        self.assertEqual(self.labels("Genesis chapter 5 based three"), ["Genesis 5:3"])
        self.assertEqual(self.labels("my best 2 friends"), [])
        text = ("I am reading Genesis Chapter 5 based through and I read from the book of "
                "Jud chapter 2 best one and also from the book of John chapter 5 best with Zeng.")
        # "based through" / "best with Zeng" are too garbled; Jude has no chapter 2.
        self.assertEqual(self.labels(text), ["Genesis 5:1-32", "John 5:1-47"])

    def test_and_between_chapters_lists_each_chapter(self):
        # Julius: "chapter 1 and 3" means chapters 1 and 3, not 1 through 3.
        self.assertEqual(self.labels("Machu Chapter 1 and 3"), ["Matthew 1:1-25", "Matthew 3:1-17"])
        self.assertEqual(self.labels("Genesis 1 and 2"), ["Genesis 1:1-31", "Genesis 2:1-25"])
        self.assertEqual(self.labels("Psalm 1 and 3 and 5"), ["Psalms 1:1-6", "Psalms 3:1-8", "Psalms 5:1-12"])
        self.assertEqual(self.labels("Genesis 50 and 51"), ["Genesis 50:1-26"])   # 51 doesn't exist
        self.assertEqual(self.labels("John 3:16 and 17"), ["John 3:16-17"])       # verses: still a range
        self.assertEqual(self.labels("Jude 3 and 4"), ["Jude 1:3-4"])
        self.assertEqual(self.labels("pick numbers 1 and 2 and 3 and 4"), [])     # long list: counting

    def test_comma_after_book_name(self):
        text = ("I mentioned the book of Chapter 1, both Daniel, Chapter 2, verse 5. "
                "Both I also mentioned Machu Chapter 1 and 3.")
        self.assertEqual(self.labels(text), ["Daniel 2:5", "Matthew 1:1-25", "Matthew 3:1-17"])
        self.assertEqual(self.labels("Thank you John, 3 more things"), [])  # no "chapter": not a reference

    def test_chapter_only_ignores_counting(self):
        self.assertEqual(self.labels("we met on Acts 2 weeks ago"), [])
        self.assertEqual(self.labels("Job 2 years ago"), [])
        self.assertEqual(self.labels("pick numbers 1 through 10"), [])
        self.assertEqual(self.labels("Mark 3 or 4 of them"), [])

    def test_comma_or_space_between_chapter_and_verse(self):
        # How Whisper often writes a spoken "John three sixteen".
        self.assertEqual(self.labels("And that's also for John 3, 16."), ["John 3:16"])
        self.assertEqual(self.labels("John 3 16"), ["John 3:16"])
        self.assertEqual(self.labels("John three sixteen"), ["John 3:16"])
        self.assertEqual(self.labels("Romans 8, 28 through 30"), ["Romans 8:28-30"])
        self.assertEqual(self.labels("First Corinthians 13, 4"), ["1 Corinthians 13:4"])

    def test_number_lists_are_not_references(self):
        self.assertEqual(self.labels("write the numbers 1, 2, 3 on the board"), [])
        self.assertEqual(self.labels("Numbers 1 2 3 4"), [])
        self.assertEqual(self.labels("John 3, 99"), [])   # still checked against the KJV

    def test_ordinary_speech_is_not_a_reference(self):
        self.assertEqual(self.labels("He said the spirit of the Lord"), [])
        self.assertEqual(self.labels("Mark 5 people came in"), [])
        self.assertEqual(self.labels("for one of the people in the room"), [])

    def test_multiple_references_in_one_chunk(self):
        self.assertEqual(
            self.labels("Read John 3:16 and then Romans 5:8"),
            ["John 3:16", "Romans 5:8"],
        )

    def test_repeated_reference_counts_as_latest(self):
        self.assertEqual(
            self.labels("John 3:16, then Romans 5:8, and back to John 3:16"),
            ["Romans 5:8", "John 3:16"],
        )

    def test_whisper_number_styles(self):
        self.assertEqual(self.labels("Ephesians 6-10 to the end of the chapter."), ["Ephesians 6:10-24"])
        self.assertEqual(self.labels("Revelations 21-4."), ["Revelation 21:4"])
        self.assertEqual(self.labels("Esther 8-9."), ["Esther 8:9"])
        self.assertEqual(self.labels("Amos 33."), ["Amos 3:3"])
        self.assertEqual(self.labels("Acts 18."), ["Acts 18:1-28"])          # chapter 18 exists: keep
        self.assertEqual(self.labels("Rev. 2213."), ["Revelation 22:13"])
        self.assertEqual(self.labels("John 340."), [])                        # 3:40 doesn't exist
        self.assertEqual(self.labels("John 3, Col. 16."), ["John 3:16"])
        self.assertEqual(self.labels("Romans 10, 9, and 10."), ["Romans 10:9-10"])
        self.assertEqual(self.labels("Matthew 5 verse 3. Then verse 8."), ["Matthew 5:3", "Matthew 5:8"])
        self.assertEqual(self.labels("John 3:16-18"), ["John 3:16-18"])       # verse range unchanged
        self.assertEqual(self.labels("We have 33 members"), [])
        self.assertEqual(self.labels("Psalm 23 verse 1-6."), ["Psalms 23:1-6"])
        self.assertEqual(self.labels("Matthew 5 verses 3-12."), ["Matthew 5:3-12"])
        self.assertEqual(self.labels("Genesis chapters 1-3."), ["Genesis 1:1-3:24"])
        self.assertEqual(self.labels("The Bible says in John 14, 6, I am the way."), ["John 14:6"])

    def test_number_words(self):
        self.assertEqual(words_to_digits("one hundred and nineteen"), "119")
        self.assertEqual(words_to_digits("twenty-three"), "23")
        self.assertEqual(words_to_digits("three sixteen"), "3 16")
        self.assertEqual(words_to_digits("eight twenty eight"), "8 28")
        self.assertEqual(words_to_digits("one hundred nineteen one hundred five"), "119 105")


if __name__ == "__main__":
    unittest.main()
